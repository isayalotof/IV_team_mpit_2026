import io
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, delete
from askdata.auth.deps import require_role, get_current_user
from askdata.auth.models import User
from askdata.auth.service import role_gte
from askdata.db.meta import get_session
from askdata.db.target import execute_read_only
from askdata.reports.models import SavedReport
from askdata.query.visualizer import build_chart_config
from askdata.query.pipeline import _extract_columns_from_rows, _rows_to_list

router = APIRouter(prefix="/reports", tags=["reports"])


class CreateReportRequest(BaseModel):
    name: str
    description: str | None = None
    query_id: str | None = None
    sql: str | None = None
    original_question: str | None = None
    is_public: bool = False
    interpretation: dict | None = None
    chart_config: dict | None = None
    columns_meta: list | None = None


class UpdateReportRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


def _report_to_dict(r: SavedReport, has_schedule: bool = False) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "owner": {"id": r.owner_id, "username": r.owner_username},
        "is_public": r.is_public,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
        "chart_type": (r.chart_config or {}).get("type", "table"),
        "has_schedule": has_schedule,
        "original_question": r.original_question,
    }


@router.get("")
async def list_reports(
    scope: str = "all",
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    q = select(SavedReport)
    if scope == "mine":
        q = q.where(SavedReport.owner_id == current_user.id)
    elif scope == "public":
        q = q.where(SavedReport.is_public == True)
    else:
        if not role_gte(current_user.role, "analyst"):
            q = q.where(
                or_(SavedReport.is_public == True, SavedReport.owner_id == current_user.id)
            )
    q = q.order_by(SavedReport.created_at.desc())
    result = await session.execute(q)
    reports = result.scalars().all()
    return {"reports": [_report_to_dict(r) for r in reports]}


@router.post("")
async def create_report(
    body: CreateReportRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    if not body.sql:
        raise HTTPException(status_code=400, detail="sql is required")

    report = SavedReport(
        id=f"r_{uuid.uuid4().hex[:8]}",
        name=body.name,
        description=body.description,
        owner_id=current_user.id,
        owner_username=current_user.username,
        is_public=body.is_public,
        sql=body.sql,
        original_question=body.original_question,
        interpretation=body.interpretation,
        chart_config=body.chart_config,
        columns_meta=body.columns_meta,
    )
    session.add(report)
    await session.commit()
    return _report_to_dict(report)


@router.get("/{report_id}")
async def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.is_public and report.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    return {**_report_to_dict(report), "sql": report.sql, "interpretation": report.interpretation, "chart_config": report.chart_config}


@router.patch("/{report_id}")
async def update_report(
    report_id: str,
    body: UpdateReportRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    if body.name is not None:
        report.name = body.name
    if body.description is not None:
        report.description = body.description
    if body.is_public is not None:
        report.is_public = body.is_public
    await session.commit()
    return _report_to_dict(report)


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    await session.delete(report)
    await session.commit()
    return {"ok": True}


@router.get("/{report_id}/export")
async def export_report_pdf(
    report_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.is_public and report.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        rows_raw = await execute_read_only(report.sql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL execution error: {e}")

    rows_list = _rows_to_list(rows_raw)
    pdf_bytes = await _generate_report_pdf(report, rows_list)

    safe_name = "".join(c if (c.isascii() and (c.isalnum() or c in "-_ ")) else "_" for c in report.name).strip("_") or "report"
    safe_name = safe_name[:50]
    from urllib.parse import quote as _quote
    encoded_name = _quote(f"{report.name}.pdf", safe="")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{safe_name}.pdf\"; filename*=UTF-8''{encoded_name}"},
    )


async def _generate_report_pdf(report, rows: list) -> bytes:
    import asyncio
    return await asyncio.to_thread(_render_report_pdf_sync, report, rows)


def _render_report_pdf_sync(report, rows: list) -> bytes:
    import io as _io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib import rcParams
    from datetime import datetime, timezone

    # DejaVu Sans — bundled with matplotlib, full Cyrillic support
    rcParams["font.family"] = "DejaVu Sans"
    rcParams["font.size"] = 10

    ACCENT = "#E8FF5C"        # acid lime
    DARK   = "#0B0D10"
    HEADER = "#181C22"
    GRAY1  = "#F2F4F7"
    GRAY2  = "#FFFFFF"
    TEXT   = "#1a1a1a"
    MUTED  = "#666666"

    buf = _io.BytesIO()
    ts = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    with PdfPages(buf) as pdf:
        # ── Cover page ──────────────────────────────────────────────────────────
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        fig.patch.set_facecolor(DARK)
        ax.set_facecolor(DARK)
        ax.axis("off")

        # Accent bar top
        ax.axhline(y=0.92, xmin=0.08, xmax=0.92, color=ACCENT, linewidth=4)

        # Title
        ax.text(0.5, 0.78, report.name,
                transform=ax.transAxes, fontsize=26, fontweight="bold",
                ha="center", va="center", color="white",
                wrap=True)

        if report.description:
            ax.text(0.5, 0.68, report.description,
                    transform=ax.transAxes, fontsize=13,
                    ha="center", va="center", color="#aaaaaa")

        # Stats box
        stats = [
            ("Строк данных", str(len(rows))),
            ("Экспортировано", ts),
            ("Источник", "AskData NL→SQL"),
        ]
        for i, (k, v) in enumerate(stats):
            y = 0.52 - i * 0.07
            ax.text(0.28, y, k + ":", transform=ax.transAxes,
                    fontsize=11, ha="right", va="center", color=MUTED)
            ax.text(0.30, y, v, transform=ax.transAxes,
                    fontsize=11, ha="left", va="center", color="white")

        # Footer
        ax.axhline(y=0.08, xmin=0.08, xmax=0.92, color="#333333", linewidth=1)
        ax.text(0.5, 0.04, "AskData — NL→SQL Analytics · Drivee",
                transform=ax.transAxes, fontsize=9,
                ha="center", va="center", color="#555555")

        pdf.savefig(fig, bbox_inches="tight", facecolor=DARK)
        plt.close(fig)

        if not rows:
            buf.seek(0)
            return buf.read()

        # ── Chart page ──────────────────────────────────────────────────────────
        try:
            from askdata.schedules.scheduler import _render_chart_png
            chart_png = _render_chart_png(report.name, rows, report.chart_config)
            if chart_png:
                from PIL import Image as PILImage
                img = PILImage.open(_io.BytesIO(chart_png))
                fig2, ax2 = plt.subplots(figsize=(11.69, 8.27))  # landscape
                fig2.patch.set_facecolor("white")
                ax2.set_facecolor("white")
                ax2.imshow(img)
                ax2.axis("off")
                # Title bar
                fig2.text(0.5, 0.97, report.name, ha="center", va="top",
                          fontsize=14, fontweight="bold", color=TEXT)
                fig2.text(0.5, 0.01, f"AskData · {ts}", ha="center", va="bottom",
                          fontsize=8, color=MUTED)
                pdf.savefig(fig2, bbox_inches="tight")
                plt.close(fig2)
        except Exception:
            pass

        # ── Data table pages ────────────────────────────────────────────────────
        all_cols = list(rows[0].keys())
        MAX_COLS = 10
        cols = all_cols[:MAX_COLS]
        ROWS_PER_PAGE = 45
        total_pages = (len(rows) + ROWS_PER_PAGE - 1) // ROWS_PER_PAGE

        for page_idx in range(total_pages):
            chunk = rows[page_idx * ROWS_PER_PAGE:(page_idx + 1) * ROWS_PER_PAGE]

            # Landscape A4 for tables
            fig3, ax3 = plt.subplots(figsize=(11.69, 8.27))
            fig3.patch.set_facecolor("white")
            ax3.set_facecolor("white")
            ax3.axis("off")

            # Header text
            page_label = f"Стр. {page_idx + 1} / {total_pages}"
            fig3.text(0.05, 0.97, report.name, ha="left", va="top",
                      fontsize=12, fontweight="bold", color=TEXT)
            fig3.text(0.95, 0.97, page_label, ha="right", va="top",
                      fontsize=9, color=MUTED)

            cell_data = [
                [str(r.get(c, "") if r.get(c) is not None else "")[:40] for c in cols]
                for r in chunk
            ]

            tbl = ax3.table(
                cellText=cell_data,
                colLabels=cols,
                cellLoc="left",
                loc="upper center",
                bbox=[0, 0.0, 1, 0.92],
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(9)
            tbl.auto_set_column_width(list(range(len(cols))))

            for (row_idx, col_idx), cell in tbl.get_celld().items():
                cell.set_edgecolor("#dddddd")
                cell.set_linewidth(0.5)
                if row_idx == 0:
                    cell.set_facecolor(HEADER)
                    cell.set_text_props(color="white", fontweight="bold", fontsize=9)
                    cell.set_height(0.055)
                elif row_idx % 2 == 0:
                    cell.set_facecolor(GRAY1)
                else:
                    cell.set_facecolor(GRAY2)

            if len(all_cols) > MAX_COLS:
                fig3.text(0.5, 0.005,
                          f"Показаны {MAX_COLS} из {len(all_cols)} колонок · "
                          f"строки {page_idx*ROWS_PER_PAGE+1}–{min((page_idx+1)*ROWS_PER_PAGE, len(rows))} "
                          f"из {len(rows)}",
                          ha="center", va="bottom", fontsize=8, color=MUTED)
            else:
                fig3.text(0.5, 0.005,
                          f"Строки {page_idx*ROWS_PER_PAGE+1}–{min((page_idx+1)*ROWS_PER_PAGE, len(rows))} "
                          f"из {len(rows)} · AskData",
                          ha="center", va="bottom", fontsize=8, color=MUTED)

            pdf.savefig(fig3, bbox_inches="tight")
            plt.close(fig3)

    buf.seek(0)
    return buf.read()


@router.post("/{report_id}/run")
async def run_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if not report.is_public and report.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        rows_raw = await execute_read_only(report.sql)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SQL execution error: {e}")

    columns = _extract_columns_from_rows(rows_raw)
    rows_list = _rows_to_list(rows_raw)
    chart_config = build_chart_config(columns, rows_list)

    # Update last_run_at
    report.last_run_at = datetime.now(timezone.utc)
    await session.commit()

    return {
        "report_id": report_id,
        "data": {"columns": columns, "rows": rows_list, "row_count": len(rows_list)},
        "chart": chart_config,
        "sql": report.sql,
    }

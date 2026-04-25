import asyncio
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from askdata.auth.deps import require_role, get_current_user
from askdata.auth.models import User
from askdata.auth.service import role_gte
from askdata.db.meta import get_session
from askdata.db.target import execute_read_only
from askdata.reports.models import SavedReport
from askdata.dashboards.models import Dashboard, DashboardWidget
from askdata.query.visualizer import build_chart_config
from askdata.query.pipeline import _extract_columns_from_rows, _rows_to_list

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


class CreateDashboardRequest(BaseModel):
    name: str
    description: str | None = None
    is_public: bool = False


class UpdateDashboardRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_public: bool | None = None


class AddWidgetRequest(BaseModel):
    report_id: str
    title_override: str | None = None


def _dash_dict(d: Dashboard, widget_count: int = 0) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "owner": {"id": d.owner_id, "username": d.owner_username},
        "is_public": d.is_public,
        "widget_count": widget_count,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


def _widget_dict(w: DashboardWidget, report: SavedReport | None = None) -> dict:
    d = {
        "id": w.id,
        "dashboard_id": w.dashboard_id,
        "report_id": w.report_id,
        "position": w.position,
        "title_override": w.title_override,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }
    if report:
        d["report"] = {
            "id": report.id,
            "name": report.name,
            "chart_type": (report.chart_config or {}).get("type", "table"),
            "chart_config": report.chart_config,
            "columns_meta": report.columns_meta,
            "sql": report.sql,
            "original_question": report.original_question,
        }
    return d


@router.get("")
async def list_dashboards(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import or_
    q = (
        select(Dashboard, func.count(DashboardWidget.id).label("wc"))
        .outerjoin(DashboardWidget, DashboardWidget.dashboard_id == Dashboard.id)
        .group_by(Dashboard.id)
    )
    if not role_gte(current_user.role, "admin"):
        q = q.where(or_(Dashboard.is_public == True, Dashboard.owner_id == current_user.id))  # noqa: E712
    q = q.order_by(Dashboard.updated_at.desc())
    result = await session.execute(q)
    return {"dashboards": [_dash_dict(d, int(wc)) for d, wc in result.all()]}


@router.post("")
async def create_dashboard(
    body: CreateDashboardRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    dash = Dashboard(
        id=f"d_{uuid.uuid4().hex[:8]}",
        name=body.name,
        description=body.description,
        owner_id=current_user.id,
        owner_username=current_user.username,
        is_public=body.is_public,
    )
    session.add(dash)
    await session.commit()
    return _dash_dict(dash)


@router.get("/{dashboard_id}")
async def get_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import or_
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if not dash.is_public and dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")

    widgets_result = await session.execute(
        select(DashboardWidget).where(DashboardWidget.dashboard_id == dashboard_id)
        .order_by(DashboardWidget.position)
    )
    widgets = widgets_result.scalars().all()

    report_ids = [w.report_id for w in widgets]
    reports_map: dict[str, SavedReport] = {}
    if report_ids:
        rr = await session.execute(select(SavedReport).where(SavedReport.id.in_(report_ids)))
        for r in rr.scalars().all():
            reports_map[r.id] = r

    return {
        **_dash_dict(dash, len(widgets)),
        "widgets": [_widget_dict(w, reports_map.get(w.report_id)) for w in widgets],
    }


@router.patch("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: str,
    body: UpdateDashboardRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")
    if body.name is not None:
        dash.name = body.name
    if body.description is not None:
        dash.description = body.description
    if body.is_public is not None:
        dash.is_public = body.is_public
    dash.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return _dash_dict(dash)


@router.delete("/{dashboard_id}")
async def delete_dashboard(
    dashboard_id: str,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")
    await session.execute(
        DashboardWidget.__table__.delete().where(DashboardWidget.dashboard_id == dashboard_id)
    )
    await session.delete(dash)
    await session.commit()
    return {"ok": True}


@router.post("/{dashboard_id}/widgets")
async def add_widget(
    dashboard_id: str,
    body: AddWidgetRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")

    report = (await session.execute(select(SavedReport).where(SavedReport.id == body.report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    # Count existing widgets for position
    count = (await session.execute(
        select(func.count(DashboardWidget.id)).where(DashboardWidget.dashboard_id == dashboard_id)
    )).scalar_one()

    widget = DashboardWidget(
        id=f"w_{uuid.uuid4().hex[:8]}",
        dashboard_id=dashboard_id,
        report_id=body.report_id,
        position=count,
        title_override=body.title_override,
    )
    session.add(widget)
    dash.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return _widget_dict(widget, report)


@router.delete("/{dashboard_id}/widgets/{widget_id}")
async def remove_widget(
    dashboard_id: str,
    widget_id: str,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")

    widget = (await session.execute(
        select(DashboardWidget).where(
            DashboardWidget.id == widget_id,
            DashboardWidget.dashboard_id == dashboard_id,
        )
    )).scalar_one_or_none()
    if not widget:
        raise HTTPException(404, "Widget not found")

    await session.delete(widget)
    await session.commit()
    return {"ok": True}


class ReorderWidgetsRequest(BaseModel):
    order: list[str]  # widget IDs in new order


@router.patch("/{dashboard_id}/widgets/reorder")
async def reorder_widgets(
    dashboard_id: str,
    body: ReorderWidgetsRequest,
    current_user: User = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
):
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")

    widgets_result = await session.execute(
        select(DashboardWidget).where(DashboardWidget.dashboard_id == dashboard_id)
    )
    widgets_map = {w.id: w for w in widgets_result.scalars().all()}

    for pos, widget_id in enumerate(body.order):
        if widget_id in widgets_map:
            widgets_map[widget_id].position = pos

    dash.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"ok": True}


@router.post("/{dashboard_id}/run")
async def run_dashboard(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Execute all widgets and return data + chart config for each."""
    from sqlalchemy import or_
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if not dash.is_public and dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")

    widgets_result = await session.execute(
        select(DashboardWidget).where(DashboardWidget.dashboard_id == dashboard_id)
        .order_by(DashboardWidget.position)
    )
    widgets = widgets_result.scalars().all()

    report_ids = [w.report_id for w in widgets]
    reports_map: dict[str, SavedReport] = {}
    if report_ids:
        rr = await session.execute(select(SavedReport).where(SavedReport.id.in_(report_ids)))
        for r in rr.scalars().all():
            reports_map[r.id] = r

    async def _run_widget(w: DashboardWidget):
        report = reports_map.get(w.report_id)
        if not report:
            return {"widget_id": w.id, "report_id": w.report_id, "title": w.title_override or w.report_id, "error": "Report not found"}
        try:
            rows_raw = await execute_read_only(report.sql)
            columns = _extract_columns_from_rows(rows_raw)
            rows_list = _rows_to_list(rows_raw)
            chart = build_chart_config(columns, rows_list)
            return {
                "widget_id": w.id,
                "report_id": w.report_id,
                "title": w.title_override or report.name,
                "data": {"columns": columns, "rows": rows_list, "row_count": len(rows_list)},
                "chart": chart,
            }
        except Exception as e:
            return {"widget_id": w.id, "report_id": w.report_id, "error": str(e)}

    results = await asyncio.gather(*[_run_widget(w) for w in widgets])
    return {"dashboard_id": dashboard_id, "widgets": list(results)}


@router.get("/{dashboard_id}/export")
async def export_dashboard_pdf(
    dashboard_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Export dashboard to PDF (one page per widget)."""
    from sqlalchemy import or_
    dash = (await session.execute(select(Dashboard).where(Dashboard.id == dashboard_id))).scalar_one_or_none()
    if not dash:
        raise HTTPException(404, "Dashboard not found")
    if not dash.is_public and dash.owner_id != current_user.id and not role_gte(current_user.role, "admin"):
        raise HTTPException(403, "Access denied")

    run_result = await run_dashboard(dashboard_id, current_user, session)
    widgets_data = run_result["widgets"]

    pdf_bytes = await asyncio.to_thread(_generate_dashboard_pdf, dash.name, dash.description, widgets_data)
    # ASCII-safe fallback name for Content-Disposition (latin-1 only)
    safe_name = "".join(c if (c.isascii() and (c.isalnum() or c in "-_ ")) else "_" for c in dash.name).strip("_") or "dashboard"
    safe_name = safe_name[:40]
    # RFC 5987 encoded name for proper Unicode filename in modern browsers
    from urllib.parse import quote as _quote
    encoded_name = _quote(f"{dash.name}.pdf", safe="")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{safe_name}.pdf\"; filename*=UTF-8''{encoded_name}"},
    )


def _setup_matplotlib_fonts():
    """Configure matplotlib to render Cyrillic correctly using DejaVu Sans."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.unicode_minus": False,
    })


def _generate_dashboard_pdf(name: str, description: str | None, widgets_data: list) -> bytes:
    import io
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt

    _setup_matplotlib_fonts()

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # Cover page
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("#FAFAFA")
        fig.text(0.5, 0.70, name, fontsize=26, fontweight="bold", ha="center", va="center", color="#111827")
        if description:
            fig.text(0.5, 0.63, description, fontsize=12, ha="center", va="center", color="#6B7280")
        fig.text(0.5, 0.56, f"AskData  ·  {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                 fontsize=10, ha="center", va="center", color="#9CA3AF")
        fig.text(0.5, 0.51, f"{len(widgets_data)} виджетов", fontsize=10, ha="center", color="#9CA3AF")
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        for w in widgets_data:
            if w.get("error"):
                continue
            _add_widget_page(pdf, w)

    buf.seek(0)
    return buf.read()


def _add_widget_page(pdf, widget_data: dict) -> None:
    import matplotlib.pyplot as plt

    _setup_matplotlib_fonts()

    title = widget_data.get("title", "Widget")
    data = widget_data.get("data", {})
    chart = widget_data.get("chart", {})
    rows_list = data.get("rows", [])
    columns = data.get("columns", [])

    fig = plt.figure(figsize=(8.27, 11.69))
    fig.patch.set_facecolor("#FAFAFA")

    # Title
    fig.text(0.5, 0.96, title, fontsize=16, fontweight="bold", ha="center", va="top", color="#111827")
    row_count = data.get("row_count", len(rows_list))
    fig.text(0.5, 0.93, f"{row_count} rows", fontsize=9, ha="center", va="top", color="#9CA3AF")

    chart_type = chart.get("type", "table")
    has_chart = chart_type in ("bar", "line", "kpi") and rows_list

    if has_chart:
        ax = fig.add_axes([0.1, 0.55, 0.82, 0.33])
        _draw_axes_chart(ax, chart_type, chart, rows_list, columns)

    # Data table
    if rows_list and columns:
        table_top = 0.50 if has_chart else 0.88
        table_h = table_top - 0.08
        ax2 = fig.add_axes([0.04, 0.06, 0.92, table_h])
        ax2.axis("off")
        col_names = [c["name"] for c in columns[:6]]
        show_rows = rows_list[:25]
        table_data = [[str(r[i]) if i < len(r) else "" for i in range(len(col_names))] for r in show_rows]
        if table_data:
            col_w = [1.0 / len(col_names)] * len(col_names)
            tbl = ax2.table(cellText=table_data, colLabels=col_names, loc="top",
                            cellLoc="left", colWidths=col_w)
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(7)
            tbl.scale(1, 1.4)
            for j in range(len(col_names)):
                tbl[0, j].set_facecolor("#E5E7EB")
                tbl[0, j].set_text_props(fontweight="bold", color="#111827")
            for i in range(1, len(show_rows) + 1):
                for j in range(len(col_names)):
                    tbl[i, j].set_facecolor("#FFFFFF" if i % 2 == 0 else "#F9FAFB")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def _draw_axes_chart(ax, chart_type: str, chart: dict, rows_list: list, columns: list) -> None:
    import matplotlib.pyplot as plt

    col_names = [c["name"] for c in columns]
    x_col = chart.get("x") or (col_names[0] if col_names else None)
    y_col = chart.get("y") or (col_names[1] if len(col_names) > 1 else None)

    if chart_type == "kpi":
        value = rows_list[0][0] if rows_list and rows_list[0] else "—"
        label = chart.get("label") or (col_names[0] if col_names else "")
        ax.axis("off")
        ax.text(0.5, 0.55, str(value), transform=ax.transAxes, fontsize=48,
                fontweight="bold", ha="center", va="center", color="#2563EB")
        ax.text(0.5, 0.15, label, transform=ax.transAxes, fontsize=11,
                ha="center", va="bottom", color="#6B7280", fontfamily="monospace")
        return

    if not x_col or not y_col:
        ax.axis("off")
        return

    x_idx = col_names.index(x_col) if x_col in col_names else 0
    y_idx = col_names.index(y_col) if y_col in col_names else 1
    display = rows_list[:12]
    labels = [str(r[x_idx]) if x_idx < len(r) else "" for r in display]

    try:
        values = [float(r[y_idx]) if y_idx < len(r) and r[y_idx] is not None else 0.0 for r in display]
    except (TypeError, ValueError):
        ax.axis("off")
        return

    if chart_type == "line":
        ax.plot(range(len(labels)), values, color="#2563EB", linewidth=2,
                marker="o", markersize=3)
        ax.fill_between(range(len(labels)), values, alpha=0.08, color="#2563EB")
    else:
        ax.bar(range(len(labels)), values, color="#2563EB", alpha=0.85)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=7)
    ax.set_facecolor("#F8FAFC")
    ax.tick_params(axis="y", labelsize=7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, alpha=0.3, linewidth=0.5)

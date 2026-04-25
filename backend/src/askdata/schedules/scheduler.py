"""APScheduler setup and job execution."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

scheduler = AsyncIOScheduler()


def start_scheduler():
    if not scheduler.running:
        scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def _run_scheduled_report(schedule_id: str):
    from askdata.db.meta import async_session
    from askdata.db.target import execute_read_only
    from askdata.schedules.models import Schedule, RunHistory
    from askdata.reports.models import SavedReport
    from sqlalchemy import select
    from datetime import datetime, timezone

    async with async_session() as session:
        sched_result = await session.execute(select(Schedule).where(Schedule.id == schedule_id))
        sched = sched_result.scalar_one_or_none()
        if not sched or not sched.enabled:
            return

        report_result = await session.execute(select(SavedReport).where(SavedReport.id == sched.report_id))
        report = report_result.scalar_one_or_none()
        if not report:
            return

        run = RunHistory(report_id=report.id, schedule_id=schedule_id, status="pending")
        session.add(run)
        await session.commit()

        try:
            rows = await execute_read_only(report.sql)
            run.rows_returned = len(rows)
            run.status = "success"

            # Delivery
            if sched.delivery_type == "telegram" and sched.delivery_targets:
                await _deliver_telegram(sched, report, rows)
            elif sched.delivery_type == "email" and sched.delivery_targets:
                await _deliver_email(sched, report, rows)

            sched.last_run_status = "success"
        except Exception as e:
            run.status = "failure"
            run.error = str(e)
            sched.last_run_status = "failure"
        finally:
            run.finished_at = datetime.now(timezone.utc)
            sched.last_run_at = datetime.now(timezone.utc)
            await session.commit()


def _fmt_number(v) -> str:
    """Format a numeric value for display."""
    try:
        n = float(v)
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K"
        if n == int(n):
            return f"{int(n):,}".replace(",", "\u202f")
        return f"{n:,.2f}".replace(",", "\u202f")
    except (TypeError, ValueError):
        return str(v)


def _render_kpi_png(report_name: str, value, label: str) -> bytes | None:
    """Render a KPI card PNG (single big number)."""
    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 3))
        ax.set_facecolor("#12151A")
        fig.patch.set_facecolor("#0B0D10")
        ax.axis("off")

        ax.text(0.5, 0.82, report_name, transform=ax.transAxes,
                fontsize=10, ha="center", va="top", color="#B0B8C4", style="italic")
        ax.text(0.5, 0.52, _fmt_number(value), transform=ax.transAxes,
                fontsize=52, fontweight="bold", ha="center", va="center",
                color="#E8FF5C", fontfamily="monospace")
        ax.text(0.5, 0.14, label, transform=ax.transAxes,
                fontsize=11, ha="center", va="bottom", color="#8B9299",
                fontfamily="monospace")

        plt.tight_layout(pad=0.5)
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="#0B0D10")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"KPI render error: {e}")
        return None


def _render_chart_png(report_name: str, rows: list, chart_config: dict | None = None) -> bytes | None:
    """Render chart PNG. Supports bar, line, kpi. Returns None on failure."""
    if not rows:
        return None

    cols = list(rows[0].keys())
    chart_type = (chart_config or {}).get("type", "bar")

    # KPI: single row + single column, or explicit kpi type
    if chart_type == "kpi" or (len(rows) == 1 and len(cols) == 1):
        value = list(rows[0].values())[0]
        label = (chart_config or {}).get("label") or cols[0]
        return _render_kpi_png(report_name, value, label)

    if len(cols) < 2:
        # Still try KPI render for single-column multi-row as aggregated bar
        return None

    # Pick x/y from chart_config if available and valid, else fall back to col order
    x_col = (chart_config or {}).get("x")
    y_col = (chart_config or {}).get("y")
    if not x_col or x_col not in rows[0]:
        x_col = cols[0]
    if not y_col or y_col not in rows[0]:
        y_col = cols[1]

    try:
        display_rows = rows[:12]
        labels = [str(r[x_col]) for r in display_rows]
        values = [float(r[y_col]) if r[y_col] is not None else 0.0 for r in display_rows]
    except (TypeError, ValueError):
        return None

    try:
        import io
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))

        if chart_type == "line":
            ax.plot(range(len(labels)), values, color="#E8FF5C", linewidth=2.5,
                    marker="o", markersize=4, markerfacecolor="#E8FF5C", zorder=3)
            ax.fill_between(range(len(labels)), values, alpha=0.12, color="#E8FF5C")
        else:
            bars = ax.bar(range(len(labels)), values, color="#E8FF5C",
                          edgecolor="#0B0D10", linewidth=0.5)
            for bar in bars:
                bar.set_zorder(3)

        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8, color="#B0B8C4")
        ax.set_title(report_name, fontsize=11, fontweight="bold", color="#F0F4FA", pad=10)
        ax.set_facecolor("#12151A")
        fig.patch.set_facecolor("#0B0D10")
        ax.tick_params(axis="y", colors="#B0B8C4", labelsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: _fmt_number(v)))
        ax.spines["bottom"].set_color("#2A2F3A")
        ax.spines["left"].set_color("#2A2F3A")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.grid(True, color="#1E2228", linewidth=0.5, zorder=0)
        plt.tight_layout(pad=1.5)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="#0B0D10")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        print(f"Chart render error: {e}")
        return None


async def _deliver_telegram(sched, report, rows):
    from askdata.config import get_settings
    settings = get_settings()
    if not settings.telegram_bot_token:
        return
    try:
        from aiogram import Bot
        from aiogram.types import BufferedInputFile

        caption_lines = [f"📊 <b>{report.name}</b>", f"Строк: {len(rows)}"]
        caption = "\n".join(caption_lines)

        # Plain-text fallback table (used when chart unavailable)
        text_lines = [f"📊 <b>{report.name}</b>", f"Строк: {len(rows)}"]
        if rows:
            cols = list(rows[0].keys())
            header = " | ".join(str(c) for c in cols[:5])
            text_lines.append(f"\n<pre>{header}")
            for row in rows[:5]:
                text_lines.append(" | ".join(str(row[c]) for c in cols[:5]))
            text_lines.append("</pre>")
        text_summary = "\n".join(text_lines)

        chart_bytes = _render_chart_png(report.name, rows, report.chart_config)

        async with Bot(token=settings.telegram_bot_token) as bot:
            for chat_id in sched.delivery_targets:
                cid = int(chat_id) if str(chat_id).lstrip('-').isdigit() else chat_id
                if chart_bytes:
                    photo = BufferedInputFile(chart_bytes, filename="report.png")
                    await bot.send_photo(chat_id=cid, photo=photo, caption=caption, parse_mode="HTML")
                else:
                    await bot.send_message(chat_id=cid, text=text_summary, parse_mode="HTML")
    except Exception as e:
        print(f"Telegram delivery error: {e}")


async def _deliver_email(sched, report, rows):
    from askdata.config import get_settings
    settings = get_settings()
    if not settings.smtp_user:
        return
    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        msg = MIMEText(f"Отчёт: {report.name}\nСтрок: {len(rows)}", "plain", "utf-8")
        msg["Subject"] = f"AskData: {report.name}"
        msg["From"] = settings.smtp_user
        for target in sched.delivery_targets:
            msg["To"] = target
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_password,
                start_tls=True,
            )
    except Exception:
        pass


def add_schedule_job(schedule_id: str, cron: str, timezone_str: str = "Europe/Moscow"):
    try:
        tz = pytz.timezone(timezone_str)
    except Exception:
        tz = pytz.UTC

    parts = cron.split()
    if len(parts) == 5:
        minute, hour, day, month, day_of_week = parts
    else:
        minute, hour, day, month, day_of_week = "0", "9", "*", "*", "*"

    scheduler.add_job(
        _run_scheduled_report,
        CronTrigger(
            minute=minute, hour=hour, day=day, month=month,
            day_of_week=day_of_week, timezone=tz
        ),
        id=f"sched_{schedule_id}",
        args=[schedule_id],
        replace_existing=True,
    )


def remove_schedule_job(schedule_id: str):
    job_id = f"sched_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

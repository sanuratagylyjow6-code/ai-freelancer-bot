"""HTML-страница дашборда для статистики бота."""

import html as html_module
from datetime import datetime


def _esc(text):
    """Экранирует HTML-спецсимволы."""
    if text is None:
        return ""
    return html_module.escape(str(text))


def render_dashboard(stats):
    """Собирает HTML-страницу из статистики."""

    # --- Топ каналов: строки таблицы ---
    channels_rows = ""
    for ch, cnt in stats.get("top_channels", []):
        channels_rows += (
            "<tr>"
            "<td>@" + _esc(ch) + "</td>"
            "<td class='num'>" + str(cnt) + "</td>"
            "</tr>"
        )
    if not channels_rows:
        channels_rows = "<tr><td colspan='2'>Нет данных</td></tr>"

    # --- Типы проектов ---
    types_rows = ""
    for ptype, cnt in stats.get("projects_by_type", []):
        types_rows += (
            "<tr>"
            "<td>" + _esc(ptype) + "</td>"
            "<td class='num'>" + str(cnt) + "</td>"
            "</tr>"
        )
    if not types_rows:
        types_rows = "<tr><td colspan='2'>Нет проектов</td></tr>"

    # --- Последние вакансии ---
    recent_rows = ""
    for ch, cat, title, url, found in stats.get("recent_jobs", []):
        short_title = title[:70] + ("..." if len(title) > 70 else "")
        recent_rows += (
            "<div class='recent-item'>"
            "<a href='" + _esc(url) + "' target='_blank'>"
            "<b>" + _esc(short_title) + "</b>"
            "</a>"
            "<div class='meta'>" + _esc(cat) + " &middot; @" + _esc(ch) + " &middot; " + _esc(found) + "</div>"
            "</div>"
        )
    if not recent_rows:
        recent_rows = "<p>Нет данных</p>"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Проценты AI-фильтра
    total = max(stats.get("jobs_total", 0), 1)
    sent_pct = int(100 * stats.get("jobs_sent", 0) / total)
    filtered_pct = 100 - sent_pct

    # --- HTML ---
    html_page = (
        "<!DOCTYPE html>"
        "<html lang='ru'><head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>AI Freelancer Dashboard</title>"
        "<style>"
        "* { box-sizing: border-box; margin: 0; padding: 0; }"
        "body { font-family: -apple-system, system-ui, sans-serif; "
        "background: #0f1419; color: #e6e6e6; padding: 16px; line-height: 1.5; }"
        "h1 { font-size: 22px; margin-bottom: 4px; color: #fff; }"
        ".subtitle { color: #8b98a5; font-size: 13px; margin-bottom: 20px; }"
        ".grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }"
        ".card { background: #1a2029; border-radius: 10px; padding: 14px; }"
        ".card .label { color: #8b98a5; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }"
        ".card .value { font-size: 24px; font-weight: 700; color: #fff; margin-top: 4px; }"
        ".card .value.green { color: #4ade80; }"
        ".card .value.orange { color: #fb923c; }"
        ".section { background: #1a2029; border-radius: 10px; padding: 16px; margin-bottom: 14px; }"
        ".section h2 { font-size: 15px; margin-bottom: 12px; color: #fff; }"
        "table { width: 100%; border-collapse: collapse; font-size: 14px; }"
        "td { padding: 6px 0; border-bottom: 1px solid #2a3240; }"
        "td.num { text-align: right; color: #4ade80; font-weight: 600; }"
        "tr:last-child td { border-bottom: none; }"
        ".recent-item { padding: 8px 0; border-bottom: 1px solid #2a3240; }"
        ".recent-item:last-child { border-bottom: none; }"
        ".recent-item a { color: #60a5fa; text-decoration: none; font-size: 14px; }"
        ".recent-item .meta { color: #8b98a5; font-size: 12px; margin-top: 3px; }"
        ".bar { height: 8px; background: #2a3240; border-radius: 4px; overflow: hidden; margin-top: 8px; }"
        ".bar-fill { height: 100%; background: #4ade80; }"
        ".footer { color: #5d6a78; font-size: 11px; text-align: center; margin-top: 20px; }"
        "</style></head><body>"

        "<h1>🤖 AI Freelancer Dashboard</h1>"
        "<div class='subtitle'>Обновлено: " + now + "</div>"

        "<div class='grid'>"
        "<div class='card'><div class='label'>Вакансий всего</div><div class='value'>" + str(stats.get("jobs_total", 0)) + "</div></div>"
        "<div class='card'><div class='label'>За сегодня</div><div class='value green'>" + str(stats.get("jobs_today", 0)) + "</div></div>"
        "<div class='card'><div class='label'>За 7 дней</div><div class='value'>" + str(stats.get("jobs_week", 0)) + "</div></div>"
        "<div class='card'><div class='label'>Пользователей</div><div class='value'>" + str(stats.get("users_total", 0)) + "</div></div>"
        "</div>"

        "<div class='section'>"
        "<h2>🎯 AI-фильтр</h2>"
        "<table>"
        "<tr><td>Отправлено пользователям</td><td class='num'>" + str(stats.get("jobs_sent", 0)) + "</td></tr>"
        "<tr><td>Отсеяно как нерелевантное</td><td class='num'>" + str(stats.get("jobs_filtered", 0)) + "</td></tr>"
        "<tr><td>Пользователей получили рассылку</td><td class='num'>" + str(stats.get("users_notified", 0)) + "</td></tr>"
        "</table>"
        "<div class='bar'><div class='bar-fill' style='width:" + str(sent_pct) + "%'></div></div>"
        "<div class='meta' style='color:#8b98a5;font-size:12px;margin-top:4px'>"
        + str(sent_pct) + "% прошло фильтр, " + str(filtered_pct) + "% отсеяно"
        "</div>"
        "</div>"

        "<div class='section'>"
        "<h2>📡 Топ каналов</h2>"
        "<table>" + channels_rows + "</table>"
        "</div>"

        "<div class='section'>"
        "<h2>📦 Проекты</h2>"
        "<table>"
        "<tr><td>Всего проектов (однофайловых)</td><td class='num'>" + str(stats.get("projects_total", 0)) + "</td></tr>"
        "<tr><td>Многофайловых (ZIP)</td><td class='num'>" + str(stats.get("projects_full", 0)) + "</td></tr>"
        "</table>"
        "<table style='margin-top:10px'>" + types_rows + "</table>"
        "</div>"

        "<div class='section'>"
        "<h2>🕐 Последние вакансии</h2>"
        + recent_rows +
        "</div>"

        "<div class='footer'>AI Freelancer Bot &middot; auto-generated dashboard</div>"
        "</body></html>"
    )

    return html_page

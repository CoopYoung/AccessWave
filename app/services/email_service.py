"""Async email delivery service using aiosmtplib.

Email sending is a best-effort operation — failures are logged but never
propagate to callers.  Configure SMTP_HOST (and related settings) in the
environment; leave SMTP_HOST blank to disable all email delivery.
"""

import asyncio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import structlog

from app.config import settings

logger = structlog.get_logger("accesswave.email")


def _score_color(score: float) -> str:
    if score >= 80:
        return "#22c55e"   # green
    if score >= 60:
        return "#f59e0b"   # amber
    return "#ef4444"       # red


def _score_label(score: float) -> str:
    if score >= 80:
        return "Good"
    if score >= 60:
        return "Fair"
    return "Poor"


def _build_scan_completed_html(
    site_name: str,
    site_url: str,
    scan_id: int,
    score: float,
    pages_scanned: int,
    total_issues: int,
    critical_count: int,
    serious_count: int,
    dashboard_url: str,
) -> str:
    color = _score_color(score)
    label = _score_label(score)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Scan Complete – AccessWave</title>
</head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;">
    <tr><td align="center" style="padding:40px 16px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden;max-width:600px;">
        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px 40px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;letter-spacing:-0.5px;">
              AccessWave
            </h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,.8);font-size:14px;">
              WCAG 2.1 Accessibility Scanner
            </p>
          </td>
        </tr>
        <!-- Body -->
        <tr>
          <td style="padding:40px 40px 32px;">
            <h2 style="margin:0 0 8px;color:#0f172a;font-size:20px;font-weight:600;">
              Scan complete &#10003;
            </h2>
            <p style="margin:0 0 24px;color:#64748b;font-size:15px;">
              Your scan for <strong style="color:#0f172a;">{site_name}</strong>
              (<a href="{site_url}" style="color:#6366f1;">{site_url}</a>) has finished.
            </p>

            <!-- Score badge -->
            <table role="presentation" cellpadding="0" cellspacing="0"
                   style="margin:0 auto 24px;text-align:center;">
              <tr>
                <td style="background:{color};border-radius:50%;width:96px;height:96px;vertical-align:middle;text-align:center;">
                  <span style="display:block;color:#ffffff;font-size:32px;font-weight:700;line-height:96px;">
                    {score:.0f}
                  </span>
                </td>
              </tr>
              <tr>
                <td style="padding-top:8px;color:{color};font-size:14px;font-weight:600;text-align:center;">
                  {label}
                </td>
              </tr>
            </table>

            <!-- Stats grid -->
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="margin-bottom:32px;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">
              <tr style="background:#f8fafc;">
                <td style="padding:12px 16px;text-align:center;border-right:1px solid #e2e8f0;">
                  <div style="font-size:22px;font-weight:700;color:#0f172a;">{pages_scanned}</div>
                  <div style="font-size:12px;color:#64748b;margin-top:2px;">Pages scanned</div>
                </td>
                <td style="padding:12px 16px;text-align:center;border-right:1px solid #e2e8f0;">
                  <div style="font-size:22px;font-weight:700;color:#0f172a;">{total_issues}</div>
                  <div style="font-size:12px;color:#64748b;margin-top:2px;">Total issues</div>
                </td>
                <td style="padding:12px 16px;text-align:center;border-right:1px solid #e2e8f0;">
                  <div style="font-size:22px;font-weight:700;color:#ef4444;">{critical_count}</div>
                  <div style="font-size:12px;color:#64748b;margin-top:2px;">Critical</div>
                </td>
                <td style="padding:12px 16px;text-align:center;">
                  <div style="font-size:22px;font-weight:700;color:#f97316;">{serious_count}</div>
                  <div style="font-size:12px;color:#64748b;margin-top:2px;">Serious</div>
                </td>
              </tr>
            </table>

            <div style="text-align:center;">
              <a href="{dashboard_url}"
                 style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;
                        font-size:15px;font-weight:600;padding:12px 28px;border-radius:8px;">
                View full results
              </a>
            </div>
          </td>
        </tr>
        <!-- Footer -->
        <tr>
          <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;text-align:center;">
            <p style="margin:0;color:#94a3b8;font-size:12px;">
              You're receiving this because email notifications are enabled in your
              <a href="{dashboard_url}#settings" style="color:#6366f1;">AccessWave account settings</a>.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_scan_failed_html(
    site_name: str,
    site_url: str,
    scan_id: int,
    error: str,
    dashboard_url: str,
) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Scan Failed – AccessWave</title>
</head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;">
    <tr><td align="center" style="padding:40px 16px;">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;box-shadow:0 2px 8px rgba(0,0,0,.08);overflow:hidden;max-width:600px;">
        <tr>
          <td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px 40px;text-align:center;">
            <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;">AccessWave</h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,.8);font-size:14px;">WCAG 2.1 Accessibility Scanner</p>
          </td>
        </tr>
        <tr>
          <td style="padding:40px 40px 32px;">
            <h2 style="margin:0 0 8px;color:#ef4444;font-size:20px;font-weight:600;">
              &#9888; Scan failed
            </h2>
            <p style="margin:0 0 24px;color:#64748b;font-size:15px;">
              The scan for <strong style="color:#0f172a;">{site_name}</strong>
              (<a href="{site_url}" style="color:#6366f1;">{site_url}</a>) encountered an error.
            </p>
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin-bottom:32px;">
              <p style="margin:0;color:#991b1b;font-size:13px;font-family:monospace;word-break:break-all;">
                {error}
              </p>
            </div>
            <div style="text-align:center;">
              <a href="{dashboard_url}"
                 style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;
                        font-size:15px;font-weight:600;padding:12px 28px;border-radius:8px;">
                Go to dashboard
              </a>
            </div>
          </td>
        </tr>
        <tr>
          <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;text-align:center;">
            <p style="margin:0;color:#94a3b8;font-size:12px;">
              You're receiving this because email notifications are enabled in your
              <a href="{dashboard_url}#settings" style="color:#6366f1;">AccessWave account settings</a>.
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


async def _send(to_address: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send one email. Returns True on success, False on failure."""
    if not settings.email_enabled:
        return False
    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_ADDRESS}>"
        msg["To"] = to_address
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_USE_TLS,
            start_tls=not settings.SMTP_USE_TLS and settings.SMTP_PORT == 587,
        )
        logger.info("email_sent", to=to_address, subject=subject)
        return True
    except Exception as exc:
        logger.warning("email_send_failed", to=to_address, subject=subject, error=str(exc))
        return False


async def send_scan_completed(
    to_address: str,
    site_name: str,
    site_url: str,
    scan_id: int,
    score: float,
    pages_scanned: int,
    total_issues: int,
    critical_count: int,
    serious_count: int,
    score_threshold: float | None = None,
) -> bool:
    """Send a scan-completed notification.

    If *score_threshold* is set, the email is only sent when the score is at
    or below that threshold.
    """
    if score_threshold is not None and score > score_threshold:
        return False  # Score is fine — don't spam the user

    dashboard_url = settings.BASE_URL
    html = _build_scan_completed_html(
        site_name=site_name,
        site_url=site_url,
        scan_id=scan_id,
        score=score,
        pages_scanned=pages_scanned,
        total_issues=total_issues,
        critical_count=critical_count,
        serious_count=serious_count,
        dashboard_url=dashboard_url,
    )
    label = _score_label(score)
    text = (
        f"Scan complete for {site_name} ({site_url})\n\n"
        f"Score: {score:.0f}/100 ({label})\n"
        f"Pages scanned: {pages_scanned}\n"
        f"Total issues: {total_issues}  (Critical: {critical_count}, Serious: {serious_count})\n\n"
        f"View full results: {dashboard_url}\n"
    )
    score_str = f"{score:.0f}"
    subject = f"[AccessWave] Scan complete — {site_name} scored {score_str}/100"
    return await _send(to_address, subject, html, text)


async def send_scan_failed(
    to_address: str,
    site_name: str,
    site_url: str,
    scan_id: int,
    error: str,
) -> bool:
    """Send a scan-failed notification."""
    dashboard_url = settings.BASE_URL
    html = _build_scan_failed_html(
        site_name=site_name,
        site_url=site_url,
        scan_id=scan_id,
        error=error,
        dashboard_url=dashboard_url,
    )
    text = (
        f"Scan failed for {site_name} ({site_url})\n\n"
        f"Error: {error}\n\n"
        f"Go to your dashboard: {dashboard_url}\n"
    )
    subject = f"[AccessWave] Scan failed — {site_name}"
    return await _send(to_address, subject, html, text)

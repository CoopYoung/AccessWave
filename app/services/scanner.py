"""WCAG 2.1 accessibility scanner engine.

Checks a page's HTML against common WCAG 2.1 Level A and AA rules.
Each rule returns a list of Issue dicts.
"""

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import structlog
from bs4 import BeautifulSoup, Tag

logger = structlog.get_logger("accesswave.scanner")


@dataclass
class IssueFound:
    rule_id: str
    severity: str  # critical, serious, moderate, minor
    wcag_criteria: str
    message: str
    element_html: str | None = None
    selector: str | None = None
    how_to_fix: str | None = None


def scan_html(html: str, page_url: str) -> list[IssueFound]:
    """Run all WCAG checks against an HTML page. Returns list of issues."""
    soup = BeautifulSoup(html, "lxml")
    issues: list[IssueFound] = []

    checks = [
        _check_images_alt,
        _check_html_lang,
        _check_page_title,
        _check_heading_order,
        _check_form_labels,
        _check_link_text,
        _check_color_contrast_hints,
        _check_aria_roles,
        _check_tables,
        _check_meta_viewport,
        _check_duplicate_ids,
        _check_tabindex,
        _check_autoplaying_media,
        _check_empty_buttons,
        _check_input_autocomplete,
        _check_skip_nav,
        _check_landmarks,
    ]

    for check in checks:
        try:
            issues.extend(check(soup, page_url))
        except Exception as e:
            logger.warning("check_error", check=check.__name__, page_url=page_url, error=str(e))

    return issues


def _el_snippet(tag: Tag, max_len: int = 200) -> str:
    """Get a short HTML snippet of an element."""
    s = str(tag)
    if len(s) > max_len:
        s = s[:max_len] + "..."
    return s


def _css_selector(tag: Tag) -> str:
    """Build a rough CSS selector for an element."""
    parts = []
    for parent in reversed(list(tag.parents)):
        if parent.name and parent.name != "[document]":
            cls = ".".join(parent.get("class", [])[:1])
            s = parent.name
            if parent.get("id"):
                s += f"#{parent['id']}"
            elif cls:
                s += f".{cls}"
            parts.append(s)
    cls = ".".join(tag.get("class", [])[:1])
    s = tag.name
    if tag.get("id"):
        s += f"#{tag['id']}"
    elif cls:
        s += f".{cls}"
    parts.append(s)
    return " > ".join(parts[-4:])


# ---- WCAG Checks ----

def _check_images_alt(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.1.1 - Images must have alt text."""
    issues = []
    for img in soup.find_all("img"):
        alt = img.get("alt")
        role = img.get("role", "")
        if alt is None and role != "presentation":
            issues.append(IssueFound(
                rule_id="img-alt",
                severity="critical",
                wcag_criteria="1.1.1",
                message="Image is missing alt attribute. Screen readers cannot describe this image.",
                element_html=_el_snippet(img),
                selector=_css_selector(img),
                how_to_fix='Add an alt="" attribute describing the image, or alt="" if decorative.',
            ))
        elif alt is not None and alt.strip() == "" and role != "presentation":
            # Empty alt on non-decorative images
            src = img.get("src", "")
            if src and not any(x in src.lower() for x in ["icon", "spacer", "pixel", "bg"]):
                issues.append(IssueFound(
                    rule_id="img-alt-empty",
                    severity="moderate",
                    wcag_criteria="1.1.1",
                    message="Image has empty alt text but may not be decorative.",
                    element_html=_el_snippet(img),
                    selector=_css_selector(img),
                    how_to_fix='If the image conveys information, add descriptive alt text. If decorative, add role="presentation".',
                ))
    # Also check inputs of type image
    for inp in soup.find_all("input", {"type": "image"}):
        if not inp.get("alt"):
            issues.append(IssueFound(
                rule_id="input-image-alt",
                severity="critical",
                wcag_criteria="1.1.1",
                message="Image input is missing alt attribute.",
                element_html=_el_snippet(inp),
                selector=_css_selector(inp),
                how_to_fix="Add an alt attribute describing the button action.",
            ))
    return issues


def _check_html_lang(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 3.1.1 - Page must have a lang attribute."""
    html_tag = soup.find("html")
    if not html_tag or not html_tag.get("lang"):
        return [IssueFound(
            rule_id="html-lang",
            severity="serious",
            wcag_criteria="3.1.1",
            message="The <html> element is missing a lang attribute. Screen readers won't know the page language.",
            how_to_fix='Add lang="en" (or appropriate language code) to the <html> element.',
        )]
    lang = html_tag.get("lang", "").strip()
    if len(lang) < 2:
        return [IssueFound(
            rule_id="html-lang-invalid",
            severity="serious",
            wcag_criteria="3.1.1",
            message=f"The lang attribute value '{lang}' is not a valid language code.",
            how_to_fix="Use a valid BCP 47 language code like 'en', 'es', 'fr'.",
        )]
    return []


def _check_page_title(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 2.4.2 - Page must have a title."""
    title = soup.find("title")
    if not title or not title.string or not title.string.strip():
        return [IssueFound(
            rule_id="page-title",
            severity="serious",
            wcag_criteria="2.4.2",
            message="Page is missing a <title> element or title is empty.",
            how_to_fix="Add a descriptive <title> element inside <head>.",
        )]
    return []


def _check_heading_order(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.3.1 - Heading levels should not skip."""
    issues = []
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    prev_level = 0
    for h in headings:
        level = int(h.name[1])
        if prev_level > 0 and level > prev_level + 1:
            issues.append(IssueFound(
                rule_id="heading-order",
                severity="moderate",
                wcag_criteria="1.3.1",
                message=f"Heading level skipped: <{h.name}> follows <h{prev_level}>.",
                element_html=_el_snippet(h),
                selector=_css_selector(h),
                how_to_fix=f"Use <h{prev_level + 1}> instead, or restructure heading hierarchy.",
            ))
        prev_level = level

    # Check if page has at least one h1
    if not soup.find("h1"):
        issues.append(IssueFound(
            rule_id="missing-h1",
            severity="moderate",
            wcag_criteria="1.3.1",
            message="Page does not have an <h1> element.",
            how_to_fix="Add a single <h1> element that describes the page content.",
        ))
    return issues


def _check_form_labels(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.3.1, 4.1.2 - Form inputs must have labels."""
    issues = []
    label_fors = {label.get("for") for label in soup.find_all("label") if label.get("for")}

    for inp in soup.find_all(["input", "select", "textarea"]):
        itype = inp.get("type", "text")
        if itype in ("hidden", "submit", "button", "reset", "image"):
            continue

        has_label = (
            inp.get("id") and inp["id"] in label_fors
            or inp.get("aria-label")
            or inp.get("aria-labelledby")
            or inp.get("title")
            or inp.find_parent("label")
        )

        if not has_label:
            issues.append(IssueFound(
                rule_id="form-label",
                severity="critical",
                wcag_criteria="4.1.2",
                message=f"Form {inp.name} element has no associated label.",
                element_html=_el_snippet(inp),
                selector=_css_selector(inp),
                how_to_fix="Add a <label> element with a matching for attribute, or use aria-label.",
            ))
    return issues


def _check_link_text(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 2.4.4 - Links must have discernible text."""
    issues = []
    bad_texts = {"click here", "here", "read more", "more", "link", "this"}

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        aria = a.get("aria-label", "").strip()
        title = a.get("title", "").strip()
        img_alt = ""
        img = a.find("img")
        if img:
            img_alt = img.get("alt", "").strip()

        accessible_name = text or aria or title or img_alt

        if not accessible_name:
            issues.append(IssueFound(
                rule_id="link-name",
                severity="critical",
                wcag_criteria="2.4.4",
                message="Link has no accessible name. Screen readers will announce it as just 'link'.",
                element_html=_el_snippet(a),
                selector=_css_selector(a),
                how_to_fix="Add visible text, aria-label, or title attribute to the link.",
            ))
        elif text.lower().strip() in bad_texts:
            issues.append(IssueFound(
                rule_id="link-text-vague",
                severity="moderate",
                wcag_criteria="2.4.4",
                message=f"Link text '{text}' is not descriptive enough.",
                element_html=_el_snippet(a),
                selector=_css_selector(a),
                how_to_fix="Use descriptive link text that explains where the link goes.",
            ))
    return issues


def _check_color_contrast_hints(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.4.3 - Flag elements with inline styles that may have contrast issues."""
    issues = []
    for el in soup.find_all(style=True):
        style = el.get("style", "")
        if "color" in style.lower() and "background" not in style.lower():
            issues.append(IssueFound(
                rule_id="color-contrast-inline",
                severity="moderate",
                wcag_criteria="1.4.3",
                message="Element has inline color without a corresponding background color. Contrast may fail.",
                element_html=_el_snippet(el),
                selector=_css_selector(el),
                how_to_fix="Ensure text and background have at least 4.5:1 contrast ratio (3:1 for large text).",
            ))
            if len(issues) > 20:
                break  # Don't overwhelm with these
    return issues


def _check_aria_roles(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 4.1.2 - ARIA roles must be valid."""
    issues = []
    valid_roles = {
        "alert", "alertdialog", "application", "article", "banner", "button",
        "cell", "checkbox", "columnheader", "combobox", "complementary",
        "contentinfo", "definition", "dialog", "directory", "document",
        "feed", "figure", "form", "grid", "gridcell", "group", "heading",
        "img", "link", "list", "listbox", "listitem", "log", "main",
        "marquee", "math", "menu", "menubar", "menuitem", "menuitemcheckbox",
        "menuitemradio", "navigation", "none", "note", "option", "presentation",
        "progressbar", "radio", "radiogroup", "region", "row", "rowgroup",
        "rowheader", "scrollbar", "search", "searchbox", "separator", "slider",
        "spinbutton", "status", "switch", "tab", "table", "tablist", "tabpanel",
        "term", "textbox", "timer", "toolbar", "tooltip", "tree", "treegrid",
        "treeitem",
    }
    for el in soup.find_all(attrs={"role": True}):
        role = el.get("role", "").strip().lower()
        if role and role not in valid_roles:
            issues.append(IssueFound(
                rule_id="aria-role-invalid",
                severity="serious",
                wcag_criteria="4.1.2",
                message=f"Invalid ARIA role: '{role}'.",
                element_html=_el_snippet(el),
                selector=_css_selector(el),
                how_to_fix=f"Use a valid WAI-ARIA role. '{role}' is not recognized.",
            ))
    return issues


def _check_tables(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.3.1 - Data tables should have headers."""
    issues = []
    for table in soup.find_all("table"):
        # Skip layout tables
        if table.get("role") == "presentation":
            continue
        if not table.find("th"):
            rows = table.find_all("tr")
            if len(rows) > 1:
                issues.append(IssueFound(
                    rule_id="table-headers",
                    severity="serious",
                    wcag_criteria="1.3.1",
                    message="Data table does not have header cells (<th>).",
                    element_html=_el_snippet(table, 100),
                    selector=_css_selector(table),
                    how_to_fix="Add <th> elements to identify row/column headers.",
                ))
    return issues


def _check_meta_viewport(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.4.4 - Viewport must allow scaling."""
    issues = []
    meta = soup.find("meta", attrs={"name": "viewport"})
    if meta:
        content = meta.get("content", "").lower()
        if "maximum-scale=1" in content.replace(" ", "") or "user-scalable=no" in content.replace(" ", ""):
            issues.append(IssueFound(
                rule_id="meta-viewport-scale",
                severity="critical",
                wcag_criteria="1.4.4",
                message="Viewport meta tag disables user scaling. Users cannot zoom in.",
                element_html=_el_snippet(meta),
                how_to_fix="Remove maximum-scale=1 and user-scalable=no from the viewport meta tag.",
            ))
    return issues


def _check_duplicate_ids(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 4.1.1 - IDs must be unique."""
    issues = []
    seen: dict[str, int] = {}
    for el in soup.find_all(id=True):
        eid = el["id"]
        seen[eid] = seen.get(eid, 0) + 1

    for eid, count in seen.items():
        if count > 1:
            issues.append(IssueFound(
                rule_id="duplicate-id",
                severity="serious",
                wcag_criteria="4.1.1",
                message=f"ID '{eid}' is used {count} times. IDs must be unique.",
                how_to_fix=f"Ensure the id='{eid}' is only used once on the page.",
            ))
    return issues


def _check_tabindex(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 2.4.3 - tabindex > 0 disrupts natural tab order."""
    issues = []
    for el in soup.find_all(attrs={"tabindex": True}):
        try:
            val = int(el.get("tabindex", 0))
        except (ValueError, TypeError):
            continue
        if val > 0:
            issues.append(IssueFound(
                rule_id="tabindex-positive",
                severity="moderate",
                wcag_criteria="2.4.3",
                message=f"Element has tabindex={val}. Positive tabindex disrupts natural tab order.",
                element_html=_el_snippet(el),
                selector=_css_selector(el),
                how_to_fix="Use tabindex='0' to add to tab order or tabindex='-1' for programmatic focus.",
            ))
    return issues


def _check_autoplaying_media(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.4.2 - Audio/video must not autoplay."""
    issues = []
    for tag in soup.find_all(["audio", "video"]):
        if tag.has_attr("autoplay"):
            issues.append(IssueFound(
                rule_id="media-autoplay",
                severity="serious",
                wcag_criteria="1.4.2",
                message=f"<{tag.name}> element autoplays. This can disorient users.",
                element_html=_el_snippet(tag),
                selector=_css_selector(tag),
                how_to_fix="Remove the autoplay attribute, or ensure the media is muted and has controls.",
            ))
    return issues


def _check_empty_buttons(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 4.1.2 - Buttons must have accessible names."""
    issues = []
    for btn in soup.find_all("button"):
        text = btn.get_text(strip=True)
        aria = btn.get("aria-label", "").strip()
        title = btn.get("title", "").strip()
        if not text and not aria and not title:
            issues.append(IssueFound(
                rule_id="button-name",
                severity="critical",
                wcag_criteria="4.1.2",
                message="Button has no accessible name.",
                element_html=_el_snippet(btn),
                selector=_css_selector(btn),
                how_to_fix="Add visible text content, aria-label, or title to the button.",
            ))
    return issues


def _check_input_autocomplete(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.3.5 - Identify input purpose via autocomplete."""
    issues = []
    purpose_types = {"name", "email", "tel", "url", "password"}
    for inp in soup.find_all("input"):
        itype = inp.get("type", "text")
        if itype in purpose_types and not inp.get("autocomplete"):
            issues.append(IssueFound(
                rule_id="input-autocomplete",
                severity="minor",
                wcag_criteria="1.3.5",
                message=f"Input type='{itype}' is missing autocomplete attribute.",
                element_html=_el_snippet(inp),
                selector=_css_selector(inp),
                how_to_fix=f"Add autocomplete attribute (e.g. autocomplete='{itype}').",
            ))
    return issues


def _check_skip_nav(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 2.4.1 - Page should have a skip navigation link."""
    # Look for skip links (usually first <a> in body pointing to #main or similar)
    body = soup.find("body")
    if not body:
        return []
    first_links = body.find_all("a", limit=5)
    has_skip = any(
        a.get("href", "").startswith("#") and
        any(w in a.get_text(strip=True).lower() for w in ("skip", "main content", "jump"))
        for a in first_links
    )
    if not has_skip:
        return [IssueFound(
            rule_id="skip-nav",
            severity="moderate",
            wcag_criteria="2.4.1",
            message="No skip navigation link found. Keyboard users must tab through all navigation.",
            how_to_fix='Add a "Skip to main content" link as the first focusable element on the page.',
        )]
    return []


def _check_landmarks(soup: BeautifulSoup, url: str) -> list[IssueFound]:
    """WCAG 1.3.1 - Page should use landmark regions."""
    issues = []
    has_main = bool(soup.find("main") or soup.find(attrs={"role": "main"}))
    has_nav = bool(soup.find("nav") or soup.find(attrs={"role": "navigation"}))

    if not has_main:
        issues.append(IssueFound(
            rule_id="landmark-main",
            severity="moderate",
            wcag_criteria="1.3.1",
            message="Page does not have a <main> landmark region.",
            how_to_fix="Wrap the primary page content in a <main> element.",
        ))
    if not has_nav:
        issues.append(IssueFound(
            rule_id="landmark-nav",
            severity="minor",
            wcag_criteria="1.3.1",
            message="Page does not have a <nav> landmark region.",
            how_to_fix="Wrap navigation links in a <nav> element.",
        ))
    return issues


def calculate_score(issues: list[IssueFound]) -> float:
    """Calculate an accessibility score 0-100 based on issues found."""
    if not issues:
        return 100.0

    weights = {"critical": 10, "serious": 5, "moderate": 2, "minor": 1}
    total_penalty = sum(weights.get(i.severity, 1) for i in issues)
    # Diminishing penalty — first issues matter most
    score = max(0, 100 - (total_penalty ** 0.7) * 3)
    return round(score, 1)

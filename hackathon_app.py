import textwrap

import streamlit as st

from hackathon_utils import (
    build_code_comparison_rows,
    clone_github_repo,
    collect_reviewable_files_from_directory,
    generate_diff,
    load_uploaded_reviewable_files,
    render_code_panel,
)
from reviewer_engine import analyze_project, get_llm_config


st.set_page_config(page_title="Agentic AI Code Reviewer", layout="wide")

DEMO_SNIPPETS = {
    "Python": (
        "snippet.py",
        textwrap.dedent(
            """
            import os
            import subprocess

            def read_config(path):
                f = open(path, "r")
                data = f.read()
                return data

            def run_user_code(code):
                return eval(code)

            def divide(a, b):
                return a / b

            def deploy(branch_name):
                try:
                    cmd = "git checkout " + branch_name
                    subprocess.call(cmd, shell=True)
                except:
                    pass

            def process(items):
                total = 0
                for i in range(len(items)):
                    total += items[i]
                return total

            print(divide(10, 0))
            """
        ).strip(),
    ),
    "JavaScript": (
        "snippet.js",
        textwrap.dedent(
            """
            const fs = require("fs");
            const { exec } = require("child_process");

            function readConfig(path) {
              return fs.readFileSync(path, "utf8");
            }

            function runUserCode(code) {
              return eval(code);
            }

            function deploy(branchName) {
              exec("git checkout " + branchName);
            }

            function divide(a, b) {
              return a / b;
            }

            console.log(divide(10, 0));
            """
        ).strip(),
    ),
    "Java": (
        "Snippet.java",
        textwrap.dedent(
            """
            import java.io.*;

            public class Snippet {
                public static String readFile(String path) throws Exception {
                    FileInputStream input = new FileInputStream(path);
                    byte[] data = input.readAllBytes();
                    return new String(data);
                }

                public static double divide(int a, int b) {
                    return a / b;
                }

                public static void main(String[] args) throws Exception {
                    Runtime.getRuntime().exec("git checkout " + args[0]);
                    System.out.println(divide(10, 0));
                }
            }
            """
        ).strip(),
    ),
    "C++": (
        "snippet.cpp",
        textwrap.dedent(
            """
            #include <cstdlib>
            #include <fstream>
            #include <iostream>
            #include <string>

            std::string readFile(const std::string& path) {
                std::ifstream file(path);
                std::string data;
                file >> data;
                return data;
            }

            int divide(int a, int b) {
                return a / b;
            }

            int main() {
                std::system("git checkout main");
                std::cout << divide(10, 0) << std::endl;
                return 0;
            }
            """
        ).strip(),
    ),
    "SQL": (
        "snippet.sql",
        textwrap.dedent(
            """
            SELECT *
            FROM users
            WHERE username = 'admin'
              AND password = '" + input_password + "';

            DELETE FROM orders;
            """
        ).strip(),
    ),
}

STYLE_PRESETS = {
    "Executive SaaS": {
        "accent": "#2563eb",
        "accent_soft": "rgba(37, 99, 235, 0.16)",
        "spot": "rgba(147, 197, 253, 0.34)",
    },
    "Security Ops": {
        "accent": "#14b8a6",
        "accent_soft": "rgba(20, 184, 166, 0.18)",
        "spot": "rgba(20, 184, 166, 0.18)",
    },
    "Hackathon Demo": {
        "accent": "#f97316",
        "accent_soft": "rgba(249, 115, 22, 0.18)",
        "spot": "rgba(251, 191, 36, 0.22)",
    },
}

THEMES = {
    "Light": {
        "bg": "#efe7db",
        "bg_top": "#faf5ee",
        "shell": "linear-gradient(180deg, rgba(255,250,245,0.8) 0%, rgba(246,238,229,0.93) 100%)",
        "card": "linear-gradient(180deg, rgba(255,252,248,0.96) 0%, rgba(250,244,236,0.99) 100%)",
        "border": "rgba(120, 98, 74, 0.14)",
        "strong_border": "rgba(37,99,235,0.10)",
        "text": "#0f1720",
        "muted": "#4f4438",
        "compare_bg": "#f8f1e8",
        "removed": "rgba(254, 226, 226, 0.92)",
        "added": "rgba(220, 252, 231, 0.95)",
        "code_text": "#0f1720",
        "shadow": "0 26px 70px rgba(78, 58, 38, 0.12)",
        "card_shadow": "0 18px 44px rgba(90, 68, 45, 0.10)",
        "gloss": "linear-gradient(180deg, rgba(255,255,255,0.75) 0%, rgba(255,255,255,0.18) 42%, rgba(255,255,255,0) 100%)",
        "input_bg": "rgba(255,250,244,0.9)",
        "editor_bg": "#2f241c",
        "editor_text": "#f7efe5",
        "editor_border": "rgba(120, 98, 74, 0.28)",
        "editor_shadow": "0 20px 48px rgba(58, 42, 29, 0.24)",
        "editor_placeholder": "rgba(247, 239, 229, 0.72)",
    },
    "Dark": {
        "bg": "#060c16",
        "bg_top": "#0b1322",
        "shell": "linear-gradient(180deg, rgba(10,18,32,0.88) 0%, rgba(8,13,23,0.96) 100%)",
        "card": "linear-gradient(180deg, rgba(17,24,39,0.88) 0%, rgba(10,15,27,0.96) 100%)",
        "border": "rgba(148,163,184,0.16)",
        "strong_border": "rgba(20,184,166,0.18)",
        "text": "#eef4ff",
        "muted": "#9eb0c5",
        "compare_bg": "#0f172a",
        "removed": "rgba(127, 29, 29, 0.58)",
        "added": "rgba(20, 83, 45, 0.62)",
        "code_text": "#eef4ff",
        "shadow": "0 26px 78px rgba(2, 6, 23, 0.58)",
        "card_shadow": "0 18px 46px rgba(2, 6, 23, 0.48)",
        "gloss": "linear-gradient(180deg, rgba(255,255,255,0.12) 0%, rgba(255,255,255,0.03) 36%, rgba(255,255,255,0) 100%)",
        "input_bg": "rgba(15,23,42,0.84)",
        "editor_bg": "linear-gradient(180deg, rgba(241, 245, 255, 0.98) 0%, rgba(224, 233, 250, 0.98) 100%)",
        "editor_text": "#162235",
        "editor_border": "rgba(125, 160, 220, 0.42)",
        "editor_shadow": "0 24px 56px rgba(2, 6, 23, 0.24)",
        "editor_placeholder": "rgba(22, 34, 53, 0.46)",
    },
}

MODE_OPTIONS = {
    "Paste code": "✍️ Code snippet",
    "Upload files": "📤 Upload",
    "Analyze local folder": "📁 Folder",
    "GitHub URL": "🌐 GitHub",
}

THEME_OPTIONS = {
    "Light": "☀️ Light",
    "Dark": "🌙 Dark",
}


def tokens(style_name: str, theme_name: str) -> dict[str, str]:
    return {**STYLE_PRESETS[style_name], **THEMES[theme_name]}


def inject_styles(t: dict[str, str]) -> None:
    st.markdown(
        f"""
        <style>
            header[data-testid="stHeader"] {{
                display: none !important;
            }}
            [data-testid="stToolbar"] {{
                display: none !important;
            }}
            .stApp > header + div {{
                margin-top: 0 !important;
            }}
            .stApp {{
                background:
                    radial-gradient(circle at top left, {t["spot"]}, transparent 26%),
                    radial-gradient(circle at top right, {t["accent_soft"]}, transparent 18%),
                    linear-gradient(180deg, {t["bg_top"]} 0%, {t["bg"]} 100%);
                color: {t["text"]};
                font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
            }}
            .block-container {{ padding-top: 0.65rem; padding-bottom: 2rem; }}
            [data-testid="stSidebar"] {{
                background:
                    linear-gradient(180deg, rgba(255,255,255,0.06) 0%, rgba(255,255,255,0.02) 100%),
                    {t["card"]};
                border-right: 1px solid {t["border"]};
            }}
            [data-testid="stSidebar"] > div:first-child {{
                background: transparent;
            }}
            [data-testid="stSidebar"], [data-testid="stSidebar"] * {{
                color: {t["text"]};
            }}
            [data-testid="stSidebar"] .sidebar-title {{
                margin: 0 0 0.2rem 0;
                font-size: 1.2rem;
                font-weight: 700;
                color: {t["text"]};
                letter-spacing: -0.02em;
            }}
            [data-testid="stSidebar"] .sidebar-copy {{
                margin: 0 0 1rem 0;
                color: {t["muted"]};
                font-size: 0.92rem;
                line-height: 1.45;
            }}
            [data-testid="stSidebar"] .sidebar-label {{
                margin: 0.85rem 0 0.4rem 0;
                color: {t["muted"]};
                font-size: 0.78rem;
                font-weight: 700;
                letter-spacing: 0.06em;
                text-transform: uppercase;
            }}
            .app-shell {{
                background: {t["shell"]};
                border: 1px solid {t["strong_border"]};
                border-radius: 28px;
                padding: 0.35rem 1.6rem 1.4rem;
                box-shadow: {t["shadow"]};
                backdrop-filter: blur(18px);
                position: relative;
                overflow: hidden;
            }}
            .app-shell::before {{
                content: "";
                position: absolute;
                inset: 0 0 auto 0;
                height: 140px;
                background: {t["gloss"]};
                pointer-events: none;
            }}
            .panel, .metric, .issue, .status, .compare-box {{
                background: {t["card"]};
                border: 1px solid {t["border"]};
                border-radius: 22px;
                box-shadow: {t["card_shadow"]};
                backdrop-filter: blur(16px);
                position: relative;
                overflow: hidden;
            }}
            .panel::before, .metric::before, .issue::before, .status::before, .compare-box::before {{
                content: "";
                position: absolute;
                inset: 0 0 auto 0;
                height: 84px;
                background: {t["gloss"]};
                pointer-events: none;
            }}
            .copy, .metric-sub, .issue-meta, .issue-body, .timeline-copy, .note {{
                color: {t["muted"]}; line-height: 1.55;
            }}
            .panel {{ padding: 1rem 1.05rem; margin-bottom: 1rem; }}
            .section-title {{ margin: 0 0 0.35rem 0; color: {t["text"]}; font-size: 1.08rem; font-weight: 700; }}
            .metric {{ padding: 1rem; min-height: 120px; }}
            .metric-label {{ color: {t["muted"]}; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }}
            .metric-value {{ margin-top: 0.55rem; font-size: 2rem; font-weight: 700; color: {t["text"]}; }}
            .metric-delta {{ margin-top: 0.45rem; color: #22c55e; font-weight: 700; }}
            .severity {{
                display: inline-block; padding: 0.28rem 0.58rem; border-radius: 999px;
                font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
            }}
            .severity-high {{ background: rgba(239,68,68,0.12); color: #ef4444; }}
            .severity-medium {{ background: rgba(245,158,11,0.12); color: #d97706; }}
            .severity-low {{ background: rgba(59,130,246,0.12); color: #3b82f6; }}
            .issue {{ padding: 1rem; margin-bottom: 0.75rem; }}
            .issue-head {{ display: flex; justify-content: space-between; gap: 0.75rem; align-items: flex-start; margin-bottom: 0.5rem; }}
            .issue-title {{ margin: 0; color: {t["text"]}; font-size: 1rem; font-weight: 700; }}
            .critical-item {{ padding: 0.82rem 0.9rem; border-radius: 16px; border: 1px solid {t["border"]}; background: {t["card"]}; margin-bottom: 0.6rem; }}
            .critical-item h4 {{ margin: 0; color: {t["text"]}; font-size: 0.95rem; }}
            .critical-item p {{ margin: 0.35rem 0 0 0; color: {t["muted"]}; font-size: 0.9rem; }}
            .style-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 0.7rem; }}
            .style-tile {{ padding: 0.9rem; border-radius: 18px; border: 1px solid {t["border"]}; background: {t["card"]}; }}
            .style-tile h4 {{ margin: 0 0 0.28rem 0; color: {t["text"]}; font-size: 0.93rem; }}
            .style-tile p {{ margin: 0; color: {t["muted"]}; font-size: 0.86rem; line-height: 1.45; }}
            .compare-box {{ overflow: hidden; }}
            .compare-head {{
                display: flex; justify-content: space-between; align-items: center;
                padding: 0.8rem 0.95rem; border-bottom: 1px solid {t["border"]};
            }}
            .compare-danger {{ background: rgba(239,68,68,0.12); }}
            .compare-safe {{ background: rgba(34,197,94,0.12); }}
            .compare-title {{ margin: 0; color: {t["text"]}; font-size: 0.95rem; font-weight: 700; }}
            .compare-sub {{ color: {t["muted"]}; font-size: 0.82rem; font-weight: 600; }}
            .compare-code {{ background: {t["compare_bg"]}; font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.84rem; }}
            .compare-row {{ display: grid; grid-template-columns: 56px 1fr; border-bottom: 1px solid {t["border"]}; }}
            .compare-row--removed {{ background: {t["removed"]}; }}
            .compare-row--added {{ background: {t["added"]}; }}
            .compare-line-number {{ padding: 0.24rem 0.6rem; color: {t["muted"]}; text-align: right; border-right: 1px solid {t["border"]}; }}
            .compare-line-text {{ padding: 0.24rem 0.75rem; white-space: pre; color: {t["code_text"]}; }}
            .timeline-step {{ display: grid; grid-template-columns: 34px 1fr; gap: 0.7rem; align-items: start; margin-bottom: 0.6rem; }}
            .timeline-num {{
                width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
                background: {t["accent"]}; color: white; font-size: 0.84rem; font-weight: 700;
            }}
            .loading-shell {{
                display: flex;
                align-items: center;
                gap: 1rem;
                padding: 1rem 1.1rem;
                margin: 0 0 1rem 0;
                background: {t["card"]};
                border: 1px solid {t["strong_border"]};
                border-radius: 22px;
                box-shadow: {t["card_shadow"]};
            }}
            .loading-orb {{
                width: 54px;
                height: 54px;
                border-radius: 50%;
                background: conic-gradient(from 0deg, color-mix(in srgb, {t["accent"]} 25%, transparent), {t["accent"]}, color-mix(in srgb, {t["accent"]} 18%, white), {t["accent"]});
                animation: spin 1.15s linear infinite;
                position: relative;
                box-shadow: 0 0 24px color-mix(in srgb, {t["accent"]} 26%, transparent);
                flex: 0 0 auto;
            }}
            .loading-orb::after {{
                content: "";
                position: absolute;
                inset: 9px;
                border-radius: 50%;
                background: {t["card"]};
            }}
            .loading-title {{
                margin: 0 0 0.2rem 0;
                color: {t["text"]};
                font-size: 1.02rem;
                font-weight: 700;
            }}
            .loading-copy {{
                margin: 0;
                color: {t["muted"]};
                line-height: 1.45;
            }}
            .loading-dots {{
                display: inline-flex;
                gap: 0.28rem;
                margin-left: 0.45rem;
                vertical-align: middle;
            }}
            .loading-dots span {{
                width: 7px;
                height: 7px;
                border-radius: 50%;
                background: {t["accent"]};
                animation: pulseDot 1.2s infinite ease-in-out;
            }}
            .loading-dots span:nth-child(2) {{ animation-delay: 0.15s; }}
            .loading-dots span:nth-child(3) {{ animation-delay: 0.3s; }}
            @keyframes spin {{
                from {{ transform: rotate(0deg); }}
                to {{ transform: rotate(360deg); }}
            }}
            @keyframes pulseDot {{
                0%, 80%, 100% {{ opacity: 0.32; transform: translateY(0); }}
                40% {{ opacity: 1; transform: translateY(-2px); }}
            }}
            .stButton > button, .stDownloadButton > button {{
                background: linear-gradient(180deg, {t["accent"]} 0%, color-mix(in srgb, {t["accent"]} 82%, black) 100%);
                color: white;
                border: 1px solid transparent;
                border-radius: 14px;
                box-shadow: 0 12px 26px color-mix(in srgb, {t["accent"]} 26%, transparent);
                font-weight: 700;
            }}
            .stButton > button:hover, .stDownloadButton > button:hover {{
                border-color: color-mix(in srgb, white 28%, {t["accent"]});
                filter: brightness(1.04);
            }}
            .stMarkdown, .stText, label, p, span, div {{
                color: inherit;
            }}
            [data-testid="stRadio"] label,
            [data-testid="stSegmentedControl"] label,
            [data-testid="stSelectbox"] label,
            [data-testid="stTextInput"] label,
            [data-testid="stTextArea"] label,
            [data-testid="stFileUploader"] label,
            .stRadio label,
            .stSegmentedControl label,
            .stSelectbox label,
            .stTextInput label,
            .stTextArea label {{
                color: {t["text"]} !important;
            }}
            [data-testid="stRadio"] p,
            [data-testid="stRadio"] span,
            [data-testid="stSegmentedControl"] p,
            [data-testid="stSegmentedControl"] span,
            [data-testid="stSelectbox"] p,
            [data-testid="stSelectbox"] span,
            [data-testid="stTextInput"] p,
            [data-testid="stTextInput"] span,
            [data-testid="stTextArea"] p,
            [data-testid="stTextArea"] span,
            [data-baseweb="select"] *,
            [role="radiogroup"] * {{
                color: {t["text"]} !important;
            }}
            [data-testid="stSidebar"] [data-baseweb="radio"] > div,
            [data-testid="stSidebar"] [data-baseweb="tab-list"] {{
                gap: 0.4rem;
                flex-wrap: wrap;
            }}
            [data-testid="stSidebar"] [data-baseweb="radio"] label,
            [data-testid="stSidebar"] button[kind="segmented_control"] {{
                background: {t["card"]} !important;
                border: 1px solid {t["border"]} !important;
                border-radius: 999px !important;
                padding: 0.35rem 0.85rem !important;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.12);
            }}
            .stTextInput input, .stSelectbox [data-baseweb="select"] > div, .stNumberInput input {{
                background: {t["input_bg"]};
                border: 1px solid {t["border"]} !important;
                border-radius: 16px !important;
                color: {t["text"]} !important;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
            }}
            .stSelectbox [data-baseweb="select"] > div {{
                background:
                    linear-gradient(180deg, color-mix(in srgb, {t["accent"]} 92%, white) 0%, {t["accent"]} 100%) !important;
                border: 1px solid color-mix(in srgb, {t["accent"]} 72%, white) !important;
                border-radius: 18px !important;
                color: white !important;
                box-shadow:
                    0 16px 34px color-mix(in srgb, {t["accent"]} 30%, transparent),
                    inset 0 1px 0 rgba(255,255,255,0.24) !important;
            }}
            .stSelectbox [data-baseweb="select"] svg,
            .stSelectbox [data-baseweb="select"] span,
            .stSelectbox [data-baseweb="select"] p {{
                color: white !important;
                fill: white !important;
            }}
            .stSelectbox [data-baseweb="select"] > div:hover {{
                filter: brightness(1.04);
            }}
            .stTextArea textarea {{
                background: {t["editor_bg"]} !important;
                border: 1px solid {t["editor_border"]} !important;
                border-radius: 20px !important;
                color: {t["editor_text"]} !important;
                box-shadow: {t["editor_shadow"]}, inset 0 1px 0 rgba(255,255,255,0.08);
                font-family: "IBM Plex Mono", Consolas, monospace;
                line-height: 1.6;
                caret-color: {t["accent"]};
            }}
            .stTextArea textarea::placeholder {{
                color: {t["editor_placeholder"]} !important;
            }}
            .stRadio > div, .stFileUploader, [data-testid="stExpander"] {{
                background: transparent;
                color: {t["text"]};
            }}
            .stCaption, .stCaption p, [data-testid="stCaptionContainer"] {{
                color: {t["muted"]} !important;
            }}
            .stMarkdown h2, .stMarkdown h3 {{
                letter-spacing: -0.02em;
            }}
            @media (max-width: 900px) {{
                .style-grid {{ grid-template-columns: 1fr; }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, subtext: str, delta: str | None = None) -> None:
    delta_html = f'<div class="metric-delta">{delta}</div>' if delta else ""
    st.markdown(
        f"""
        <div class="metric">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def severity_pill(severity: str) -> str:
    return f'<span class="severity severity-{severity}">{severity}</span>'


def status_banner(llm_status: dict[str, str | bool]) -> None:
    if llm_status["enabled"] and "completed" in str(llm_status["message"]).lower():
        title = "AI Review Online"
        extra_class = "status-success"
    elif llm_status["enabled"]:
        title = "AI Review Needs Attention"
        extra_class = "status-warning"
    else:
        title = "Local Review Mode"
        extra_class = "status-info"
    st.markdown(
        f"""
        <div class="status panel {extra_class}">
            <p class="section-title">{title}</p>
            <p class="copy">{llm_status["message"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def issue_card(issue: dict[str, str]) -> None:
    preview = issue["details"][:120].rstrip()
    if len(issue["details"]) > 120:
        preview += "..."
    header = f'{issue["title"]} [{issue["severity"].upper()}]'
    with st.expander(header, expanded=False):
        st.markdown(
            f"""
            <div class="issue">
                <div class="issue-head">
                    <h4 class="issue-title">{issue["title"]}</h4>
                    {severity_pill(issue["severity"])}
                </div>
                <p class="issue-meta">{issue["category"]} from {issue["source"]}</p>
                <p class="issue-body">{preview}</p>
                <p class="issue-body">{issue["details"]}</p>
                <p class="issue-body"><strong>Suggested fix:</strong> {issue["suggestion"]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def timeline(steps: list[str]) -> None:
    parts = []
    for index, step in enumerate(steps, start=1):
        parts.append(
            f"""
            <div class="timeline-step">
                <div class="timeline-num">{index}</div>
                <div class="timeline-copy">{step}</div>
            </div>
            """
        )
    st.markdown("".join(parts), unsafe_allow_html=True)


def risk_level(issues: list[dict[str, str]]) -> str:
    severities = [item["severity"] for item in issues]
    if "high" in severities:
        return "High Risk"
    if "medium" in severities:
        return "Moderate Risk"
    return "Low Risk"


def loading_panel(message: str, detail: str) -> str:
    return f"""
    <div class="loading-shell">
        <div class="loading-orb"></div>
        <div>
            <p class="loading-title">{message}<span class="loading-dots"><span></span><span></span><span></span></span></p>
            <p class="loading-copy">{detail}</p>
        </div>
    </div>
    """


def choice_control(label: str, options_map: dict[str, str], key: str, default: str, horizontal: bool = False) -> str:
    option_keys = list(options_map.keys())
    segmented = getattr(st, "segmented_control", None)
    if callable(segmented):
        selected = segmented(
            label,
            options=option_keys,
            default=default,
            format_func=lambda item: options_map[item],
            selection_mode="single",
            key=key,
            label_visibility="collapsed",
        )
        return selected or default

    return st.radio(
        label,
        options=option_keys,
        index=option_keys.index(default),
        format_func=lambda item: options_map[item],
        key=key,
        label_visibility="collapsed",
        horizontal=horizontal,
    )


def compare_view(selected_review: dict[str, object]) -> None:
    rows = build_code_comparison_rows(str(selected_review["original_code"]), str(selected_review["improved_code"]))
    left_html = render_code_panel(rows, "left")
    right_html = render_code_panel(rows, "right")
    left, right = st.columns(2)
    with left:
        st.markdown(
            f"""
            <div class="compare-box">
                <div class="compare-head compare-danger">
                    <div>
                        <p class="compare-title">Risky Code</p>
                        <span class="compare-sub">Original implementation</span>
                    </div>
                    {severity_pill("high")}
                </div>
                <div class="compare-code">{left_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f"""
            <div class="compare-box">
                <div class="compare-head compare-safe">
                    <div>
                        <p class="compare-title">Improved Code</p>
                        <span class="compare-sub">Suggested safer rewrite</span>
                    </div>
                    {severity_pill("low")}
                </div>
                <div class="compare-code">{right_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


llm_config = get_llm_config()

with st.sidebar:
    st.markdown('<p class="sidebar-title">Review Settings</p>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-copy">Pick a source mode and switch appearance instantly.</p>', unsafe_allow_html=True)
    st.markdown('<p class="sidebar-label">Source</p>', unsafe_allow_html=True)
    review_mode = st.selectbox(
        "Source",
        options=list(MODE_OPTIONS.keys()),
        format_func=lambda item: MODE_OPTIONS[item],
        key="review_mode",
        label_visibility="collapsed",
    )
    st.markdown('<p class="sidebar-label">Appearance</p>', unsafe_allow_html=True)
    theme_mode = choice_control("Appearance", THEME_OPTIONS, key="theme_mode", default="Light", horizontal=True)

t = tokens("Executive SaaS", theme_mode)
inject_styles(t)

st.markdown('<div class="app-shell">', unsafe_allow_html=True)
sources: list[tuple[str, str]] = []

left_spacer, center_input, right_spacer = st.columns([0.08, 0.84, 0.08])
with center_input:
    st.markdown('<div class="panel"><p class="section-title">Analysis Intake</p><p class="copy">Choose a source, run the review loop, and present the result as a professional engineering quality report.</p></div>', unsafe_allow_html=True)
    if review_mode == "Paste code":
        demo_left, demo_right = st.columns([0.72, 0.28])
        with demo_right:
            demo_choice = st.selectbox(
                "Demo Snippet",
                options=["Custom"] + list(DEMO_SNIPPETS.keys()),
                key="demo_language",
            )
        if demo_choice != "Custom":
            snippet_name, snippet_code = DEMO_SNIPPETS[demo_choice]
            st.session_state["demo_code"] = snippet_code
            st.session_state["demo_filename"] = snippet_name
        code = st.text_area("Paste code", height=440, placeholder="def add(a, b):\n    return a + b", key="demo_code")
        snippet_name = st.session_state.get("demo_filename", "snippet.py")
        if code.strip():
            sources = [(snippet_name, code)]
    elif review_mode == "Upload files":
        uploaded_files = st.file_uploader(
            "Upload source files",
            type=["py", "js", "jsx", "ts", "tsx", "java", "cpp", "cc", "cxx", "c", "cs", "go", "rb", "php", "rs", "swift", "kt", "scala", "html", "css", "sql", "json", "yaml", "yml", "sh"],
            accept_multiple_files=True,
        )
        sources = load_uploaded_reviewable_files(uploaded_files)
    elif review_mode == "Analyze local folder":
        folder_path = st.text_input("Local project path", value="D:\\code_review")
        max_files = st.slider("Max files", min_value=1, max_value=20, value=8)
        if folder_path.strip():
            sources = collect_reviewable_files_from_directory(folder_path, max_files=max_files)
            if folder_path.strip() and not sources:
                st.warning("No reviewable source files found in that folder, or the folder is inaccessible.")
    else:
        github_url = st.text_input("GitHub repository URL", placeholder="https://github.com/owner/repo")
        max_files = st.slider("Max files", min_value=1, max_value=20, value=8)
        if github_url.strip():
            st.info("The repository will be cloned only when you run analysis.")
    analyze_clicked = st.button("Analyze Project", type="primary", use_container_width=True)

review: dict[str, object] | None = None

if analyze_clicked:
    loading_placeholder = st.empty()
    if not sources:
        if review_mode == "GitHub URL":
            if not github_url.strip():
                st.error("Enter a GitHub repository URL before running analysis.")
            else:
                loading_placeholder.markdown(
                    loading_panel("Analyzing repository", "Cloning the repo, collecting source files, and preparing the review pipeline."),
                    unsafe_allow_html=True,
                )
                with st.status("Agent workflow running...", expanded=True) as status:
                    st.write("Step 1: cloning repository from GitHub")
                    repo_dir, clone_error = clone_github_repo(github_url)
                    if clone_error:
                        status.update(label="Clone failed", state="error")
                        st.error(clone_error)
                    else:
                        st.write("Step 2: extracting reviewable source files")
                        sources = collect_reviewable_files_from_directory(repo_dir, max_files=max_files)
                        if not sources:
                            status.update(label="No reviewable files found", state="error")
                            st.error("The cloned repository did not contain any supported source files to review.")
                        else:
                            st.write("Step 3: reviewing files and generating fixes")
                            st.write("Step 4: preparing the executive dashboard")
                            review = analyze_project(sources)
                            status.update(label="Review complete", state="complete")
        else:
            st.error("Provide Python code, upload files, or point to a folder with Python files.")
    if sources and review is None:
        loading_placeholder.markdown(
            loading_panel("Analyzing source files", "Running language-aware checks, model review, and rewrite validation."),
            unsafe_allow_html=True,
        )
        with st.status("Agent workflow running...", expanded=True) as status:
            if review_mode != "GitHub URL":
                st.write("Step 1: ingesting source files")
                st.write("Step 2: running language-aware review stages")
                st.write("Step 3: requesting semantic review from Hugging Face")
                st.write("Step 4: validating the suggested rewrite path")
                review = analyze_project(sources)
            status.update(label="Review complete", state="complete")
    loading_placeholder.empty()

if review:
    summary = review["project_summary"]
    files = review["file_reviews"]
    llm_status = files[0]["llm_status"] if files else None

    st.markdown("## Risk Overview")
    metrics = st.columns(4)
    with metrics[0]:
        metric_card("Files Reviewed", str(summary["files_analyzed"]), "Source files included in this analysis run.")
    with metrics[1]:
        metric_card("Findings Detected", str(summary["issues_found"]), "Prioritized mix of static, lint, and model-assisted findings.")
    with metrics[2]:
        metric_card("Risk Level", risk_level(files[0]["issues"] if files else []), "Highest visible severity in the selected review set.")
    with metrics[3]:
        delta = summary["score_after"] - summary["score_before"]
        metric_card("Quality Delta", str(summary["score_after"]), f"Before score: {summary['score_before']}", delta=f"+{delta} after suggested rewrite" if delta >= 0 else str(delta))

    if llm_status:
        status_banner(llm_status)

    selected_path = st.selectbox("Focus file", options=[item["path"] for item in files], label_visibility="collapsed")
    selected_review = next(item for item in files if item["path"] == selected_path)
    top_findings = selected_review["issues"][:3]

    overview_left, overview_right = st.columns([1.1, 0.9])
    with overview_left:
        st.markdown('<div class="panel"><p class="section-title">Critical Risks</p><p class="copy">Lead with the findings that would matter most in a review meeting or hackathon demo.</p></div>', unsafe_allow_html=True)
        critical_html = []
        for issue in top_findings:
            critical_html.append(f'<div class="critical-item"><h4>{issue["title"]}</h4><p>{issue["details"]}</p></div>')
        st.markdown("".join(critical_html), unsafe_allow_html=True)
    with overview_right:
        validation = selected_review["validation"]
        validation_text = "PASS" if validation["status"] == "passed" else "FAIL"
        st.markdown(f'<div class="panel"><p class="section-title">Review Summary</p><p class="copy">{selected_review["summary"]}</p></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="panel"><p class="section-title">Validation Check</p><p class="note"><strong>{validation_text}</strong>: {validation["details"]}</p></div>', unsafe_allow_html=True)

    st.markdown("## Before vs After")
    st.caption("Changed lines are highlighted so the risky implementation reads as danger and the rewrite reads as safe.")
    compare_view(selected_review)

    st.markdown("## Agent Workflow")
    timeline(selected_review["agent_steps"])

    issues_col, details_col = st.columns([1.05, 0.95])
    with issues_col:
        st.markdown("## Issue Breakdown")
        for issue in selected_review["issues"]:
            issue_card(issue)
    with details_col:
        st.markdown("## Suggested Rewrite")
        st.code(selected_review["improved_code"], language="python")
        with st.expander("Open unified diff", expanded=False):
            st.code(generate_diff(selected_review["original_code"], selected_review["improved_code"]), language="diff")
        with st.expander("Raw PyLint output", expanded=False):
            st.code(selected_review["lint_output"] or "No PyLint output.")
else:
    st.markdown("## Risk Overview")
    st.empty()

st.markdown("</div>", unsafe_allow_html=True)

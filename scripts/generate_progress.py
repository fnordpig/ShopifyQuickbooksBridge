#!/usr/bin/env python3
"""
Generate an interactive HTML progress tracker for the Shopify -> QBO setup wizard.

Usage:
    python generate_progress.py --output /tmp/shopify-qbo-setup.html --step 0
    python generate_progress.py --output /tmp/shopify-qbo-setup.html --step 3
    python generate_progress.py --output /tmp/shopify-qbo-setup.html --step 6

The --step argument (0-6) controls which phase is currently active.
Steps 0 = prerequisites, 1-5 = phases, 6 = all complete.
"""

import argparse

PHASES = [
    {
        "num": 0,
        "title": "Prerequisites",
        "subtitle": "Node.js, Python, Claude CLI, git",
        "time": "~30 sec",
        "instructions": """
            <p>Claude is checking your system for required tools. You need:</p>
            <ul class="checklist">
                <li>Node.js 18+ &mdash; runs the MCP servers</li>
                <li>Python 3.10+ &mdash; runs the transform scripts</li>
                <li>npm / npx &mdash; installs and runs packages</li>
                <li>git &mdash; clones the QBO MCP server repo</li>
                <li>Claude CLI &mdash; manages MCP server connections</li>
            </ul>
            <p class="tip">If anything is missing, Claude will tell you how to install it.</p>
        """,
    },
    {
        "num": 1,
        "title": "Create Shopify Custom App",
        "subtitle": "API credentials for store access",
        "time": "3-5 min",
        "instructions": """
            <p>You'll create a custom app in your Shopify Admin to get API credentials.</p>
            <ol class="steps">
                <li>Log into your <strong>Shopify Admin</strong> dashboard</li>
                <li>Click the <strong>gear icon</strong> (Settings) in the bottom-left</li>
                <li>Go to <strong>Apps and sales channels</strong></li>
                <li>Click <strong>Develop apps</strong>
                    <span class="note">If you see "Allow custom app development", click it first</span></li>
                <li>Click <strong>Create an app</strong> &rarr; name it "QBO Sync Agent"</li>
                <li>Go to <strong>Configuration</strong> tab &rarr; <strong>Admin API integration</strong> &rarr; <strong>Configure</strong></li>
                <li>Enable scopes: <code>read_customers</code>, <code>read_orders</code>, <code>read_products</code></li>
                <li>Click <strong>Save</strong>, then go to <strong>API credentials</strong> tab</li>
                <li>Click <strong>Install app</strong> (confirm in dialog)</li>
                <li>Copy the <strong>Admin API access token</strong>
                    <span class="warning">You will only see this token ONCE. Copy it now!</span></li>
            </ol>
            <div class="code-block">
                <div class="code-label">Your token will look like this:</div>
                <code>shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx</code>
            </div>
            <p class="tip"><strong>New apps (post-Jan 2026):</strong> Copy the Client ID and Client Secret instead.
            The MCP server handles OAuth token exchange automatically.</p>
        """,
    },
    {
        "num": 2,
        "title": "Configure Shopify MCP Server",
        "subtitle": "Connect Claude to your Shopify store",
        "time": "1-2 min",
        "instructions": """
            <p>No installation needed &mdash; the server runs via <code>npx</code>.</p>
            <div class="code-block">
                <div class="code-label">Add to Claude Code (static token):</div>
                <pre>claude mcp add shopify -- npx shopify-mcp \\
  --accessToken shpat_YOUR_TOKEN \\
  --domain your-store.myshopify.com</pre>
            </div>
            <div class="code-block">
                <div class="code-label">Or with OAuth (new apps):</div>
                <pre>claude mcp add shopify -- npx shopify-mcp \\
  --clientId YOUR_CLIENT_ID \\
  --clientSecret YOUR_CLIENT_SECRET \\
  --domain your-store.myshopify.com</pre>
            </div>
            <p><strong>Verify:</strong> Ask Claude <em>"List my first 3 Shopify products"</em></p>
            <p class="tip"><strong>Common pitfall:</strong> Use the package <code>shopify-mcp</code>,
            not <code>shopify-mcp-server</code> &mdash; they're different packages.</p>
        """,
    },
    {
        "num": 3,
        "title": "Create QBO Developer App",
        "subtitle": "OAuth credentials for QuickBooks access",
        "time": "3-5 min",
        "instructions": """
            <p>You'll create a developer app on the Intuit developer portal.</p>
            <ol class="steps">
                <li>Go to <a href="https://developer.intuit.com" target="_blank">developer.intuit.com</a> and sign in</li>
                <li>Click <strong>Dashboard</strong> &rarr; <strong>Create an app</strong></li>
                <li>Select <strong>QuickBooks Online and Payments</strong></li>
                <li>Name it "Shopify Sync Agent"</li>
                <li>Under Scopes, enable <code>com.intuit.quickbooks.accounting</code></li>
                <li>Set Redirect URI to:
                    <div class="code-block inline">
                        <code>https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl</code>
                    </div>
                </li>
                <li>Click <strong>Create app</strong></li>
                <li>Go to <strong>Keys &amp; credentials</strong></li>
                <li>Use the <strong>Development</strong> tab for sandbox testing</li>
                <li>Copy the <strong>Client ID</strong> and <strong>Client Secret</strong></li>
            </ol>
            <p class="tip">Start with Development/Sandbox credentials. You can switch to
            Production later when you're ready for real data.</p>
        """,
    },
    {
        "num": 4,
        "title": "Install & Configure QBO MCP Server",
        "subtitle": "Clone, build, authenticate",
        "time": "3-5 min",
        "instructions": """
            <p>Unlike Shopify, the QBO MCP server needs to be cloned and built locally.</p>

            <h4>Step 1: Clone & Build</h4>
            <div class="code-block">
                <pre>git clone https://github.com/laf-rge/quickbooks-mcp.git ~/quickbooks-mcp
cd ~/quickbooks-mcp && npm install && npm run build</pre>
            </div>

            <h4>Step 2: Save Credentials</h4>
            <div class="code-block">
                <div class="code-label">Create ~/.quickbooks-mcp/credentials.json:</div>
                <pre>{
  "client_id": "YOUR_QBO_CLIENT_ID",
  "client_secret": "YOUR_QBO_CLIENT_SECRET",
  "redirect_url": "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
}</pre>
            </div>

            <h4>Step 3: Add to Claude</h4>
            <div class="code-block">
                <pre>claude mcp add quickbooks -- node ~/quickbooks-mcp/dist/index.js</pre>
            </div>

            <h4>Step 4: OAuth Flow</h4>
            <ol class="steps">
                <li>Restart Claude Code</li>
                <li>Tell Claude: <em>"Authenticate with QuickBooks"</em></li>
                <li>A browser window opens &mdash; authorize the app</li>
                <li>Tokens are saved automatically</li>
            </ol>
            <p class="warning">Complete the browser authorization quickly &mdash; the auth code expires in minutes.</p>

            <h4>Step 5: Verify</h4>
            <p>Ask Claude: <em>"How many customers do I have in QuickBooks?"</em></p>
        """,
    },
    {
        "num": 5,
        "title": "Verify & Test",
        "subtitle": "End-to-end pipeline check",
        "time": "1-2 min",
        "instructions": """
            <p>Run a small test to confirm everything works together.</p>
            <ol class="steps">
                <li>Claude pulls 3 test customers from Shopify</li>
                <li>Runs the transform scripts locally</li>
                <li>Reviews the output with you</li>
                <li>Optionally loads 1 test record into QBO sandbox</li>
            </ol>
            <p>When this passes, you're ready for production syncs.</p>
            <div class="code-block">
                <div class="code-label">To run a full sync later, just say:</div>
                <pre>"Sync my Shopify customers and orders to QuickBooks Online"</pre>
            </div>
        """,
    },
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shopify to QBO &mdash; Setup Wizard</title>
<style>
:root {{
  --bg: #0f172a;
  --surface: #1e293b;
  --surface-hover: #273548;
  --border: #334155;
  --text: #f1f5f9;
  --text-muted: #94a3b8;
  --accent: #3b82f6;
  --accent-glow: rgba(59, 130, 246, 0.15);
  --success: #22c55e;
  --success-bg: rgba(34, 197, 94, 0.1);
  --warning: #f59e0b;
  --warning-bg: rgba(245, 158, 11, 0.1);
  --error: #ef4444;
  --pending: #64748b;
  --radius: 12px;
  --font: 'Inter', system-ui, -apple-system, sans-serif;
  --mono: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
}}

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  line-height: 1.6;
  min-height: 100vh;
}}

.wizard {{
  max-width: 760px;
  margin: 0 auto;
  padding: 40px 24px 80px;
}}

header {{
  text-align: center;
  margin-bottom: 48px;
}}

header h1 {{
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--accent), #a78bfa);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}

header h2 {{
  font-size: 15px;
  font-weight: 400;
  color: var(--text-muted);
  margin-top: 4px;
}}

.progress-container {{
  margin-top: 32px;
}}

.progress-bar {{
  height: 6px;
  background: var(--border);
  border-radius: 3px;
  overflow: hidden;
}}

.progress-fill {{
  height: 100%;
  background: linear-gradient(90deg, var(--accent), #a78bfa);
  border-radius: 3px;
  transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}}

.progress-label {{
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-muted);
}}

.phase {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}}

.phase.active {{
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent), 0 4px 24px var(--accent-glow);
}}

.phase.complete {{
  border-color: var(--success);
  opacity: 0.85;
}}

.phase-header {{
  display: flex;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  user-select: none;
  gap: 16px;
}}

.phase-header:hover {{
  background: var(--surface-hover);
}}

.phase-icon {{
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
  transition: all 0.3s ease;
}}

.pending .phase-icon {{
  background: var(--border);
  color: var(--text-muted);
}}

.active .phase-icon {{
  background: var(--accent);
  color: white;
  animation: pulse 2s ease-in-out infinite;
}}

.complete .phase-icon {{
  background: var(--success);
  color: white;
}}

@keyframes pulse {{
  0%, 100% {{ box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }}
  50% {{ box-shadow: 0 0 0 8px rgba(59, 130, 246, 0); }}
}}

.phase-info {{
  flex: 1;
}}

.phase-title {{
  font-size: 15px;
  font-weight: 600;
}}

.phase-subtitle {{
  font-size: 13px;
  color: var(--text-muted);
}}

.phase-meta {{
  font-size: 12px;
  color: var(--text-muted);
  text-align: right;
}}

.phase-status {{
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-size: 11px;
}}

.active .phase-status {{ color: var(--accent); }}
.complete .phase-status {{ color: var(--success); }}
.pending .phase-status {{ color: var(--pending); }}

.phase-body {{
  display: none;
  padding: 0 20px 20px;
  border-top: 1px solid var(--border);
  margin-top: 0;
  animation: slideDown 0.3s ease;
}}

.phase.expanded .phase-body {{
  display: block;
}}

@keyframes slideDown {{
  from {{ opacity: 0; transform: translateY(-8px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

.phase-body p {{ margin: 12px 0; font-size: 14px; color: var(--text-muted); }}
.phase-body strong {{ color: var(--text); }}

.phase-body ol.steps {{
  margin: 12px 0;
  padding-left: 24px;
}}

.phase-body ol.steps li {{
  margin: 8px 0;
  font-size: 14px;
  color: var(--text-muted);
}}

.phase-body ul.checklist {{
  list-style: none;
  margin: 12px 0;
  padding: 0;
}}

.phase-body ul.checklist li {{
  padding: 6px 0 6px 28px;
  position: relative;
  font-size: 14px;
  color: var(--text-muted);
}}

.phase-body ul.checklist li::before {{
  content: '';
  position: absolute;
  left: 4px;
  top: 10px;
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-radius: 3px;
}}

.code-block {{
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 12px 0;
  overflow: hidden;
}}

.code-block.inline {{ display: inline-block; margin: 8px 0; }}

.code-label {{
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
}}

.code-block code, .code-block pre {{
  display: block;
  padding: 12px 16px;
  font-family: var(--mono);
  font-size: 13px;
  line-height: 1.5;
  color: var(--accent);
  white-space: pre-wrap;
  word-break: break-all;
}}

.note {{
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  margin-top: 2px;
}}

.tip {{
  background: var(--accent-glow);
  border-left: 3px solid var(--accent);
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  font-size: 13px;
  color: var(--text-muted);
}}

.warning {{
  display: block;
  background: var(--warning-bg);
  border-left: 3px solid var(--warning);
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  font-size: 13px;
  color: var(--warning);
  margin: 8px 0;
}}

.phase-body h4 {{
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin: 20px 0 8px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}}

.phase-body h4:first-of-type {{
  border-top: none;
  padding-top: 0;
  margin-top: 12px;
}}

.phase-body a {{
  color: var(--accent);
  text-decoration: none;
}}

.phase-body a:hover {{
  text-decoration: underline;
}}

.complete-banner {{
  text-align: center;
  padding: 40px 20px;
  background: var(--success-bg);
  border: 1px solid var(--success);
  border-radius: var(--radius);
  margin-top: 24px;
  display: none;
}}

.complete-banner.visible {{ display: block; }}

.complete-banner h3 {{
  color: var(--success);
  font-size: 20px;
  margin-bottom: 8px;
}}

.complete-banner p {{
  color: var(--text-muted);
  font-size: 14px;
}}

footer {{
  text-align: center;
  margin-top: 48px;
  font-size: 12px;
  color: var(--pending);
}}
</style>
</head>
<body>
<div class="wizard">
  <header>
    <h1>Shopify &rarr; QuickBooks Online</h1>
    <h2>Setup Wizard</h2>
    <div class="progress-container">
      <div class="progress-bar">
        <div class="progress-fill" style="width: {progress_pct}%"></div>
      </div>
      <div class="progress-label">
        <span>{progress_text}</span>
        <span>{progress_pct}%</span>
      </div>
    </div>
  </header>

  {phases_html}

  <div class="complete-banner {banner_class}">
    <h3>Setup Complete</h3>
    <p>Your Shopify &rarr; QBO sync pipeline is ready.<br>
    Tell Claude: "Sync my Shopify customers and orders to QuickBooks Online"</p>
  </div>

  <footer>
    Shopify &rarr; QBO Sync Pipeline &middot; Setup Wizard
  </footer>
</div>

<script>
document.querySelectorAll('.phase-header').forEach(header => {{
  header.addEventListener('click', () => {{
    const phase = header.parentElement;
    phase.classList.toggle('expanded');
  }});
}});

// Auto-expand the active phase
const active = document.querySelector('.phase.active');
if (active) active.classList.add('expanded');
</script>
</body>
</html>"""


def generate_phase_html(phase: dict, current_step: int) -> str:
    num = phase["num"]
    if num < current_step:
        status_class = "complete"
        status_text = "Complete"
        icon_text = "&#10003;"
    elif num == current_step:
        status_class = "active"
        status_text = "In Progress"
        icon_text = str(num + 1) if num > 0 else "&#9881;"
    else:
        status_class = "pending"
        status_text = "Pending"
        icon_text = str(num + 1) if num > 0 else "&#9881;"

    return f"""
  <div class="phase {status_class}">
    <div class="phase-header">
      <div class="phase-icon">{icon_text}</div>
      <div class="phase-info">
        <div class="phase-title">{phase['title']}</div>
        <div class="phase-subtitle">{phase['subtitle']}</div>
      </div>
      <div class="phase-meta">
        <div class="phase-status">{status_text}</div>
        <div>{phase['time']}</div>
      </div>
    </div>
    <div class="phase-body">
      {phase['instructions']}
    </div>
  </div>"""


def main():
    parser = argparse.ArgumentParser(description="Generate setup wizard progress page")
    parser.add_argument("--output", "-o", required=True, help="Output HTML file path")
    parser.add_argument("--step", "-s", type=int, default=0, choices=range(7),
                        help="Current step (0-6). 6 = all complete.")
    args = parser.parse_args()

    current_step = args.step

    phases_html = "\n".join(generate_phase_html(p, current_step) for p in PHASES)

    total_phases = len(PHASES)
    completed = min(current_step, total_phases)
    progress_pct = round((completed / total_phases) * 100)

    if current_step >= total_phases:
        progress_text = "All phases complete"
        progress_pct = 100
        banner_class = "visible"
    else:
        progress_text = f"Phase {current_step + 1} of {total_phases}: {PHASES[current_step]['title']}"
        banner_class = ""

    html = HTML_TEMPLATE.format(
        progress_pct=progress_pct,
        progress_text=progress_text,
        phases_html=phases_html,
        banner_class=banner_class,
    )

    with open(args.output, "w") as f:
        f.write(html)

    print(f"Progress page written to: {args.output}")
    print(f"Current step: {current_step}/{total_phases}")
    if current_step < total_phases:
        print(f"Active phase: {PHASES[current_step]['title']}")


if __name__ == "__main__":
    main()

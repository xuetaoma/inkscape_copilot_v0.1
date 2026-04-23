# Inkscape Copilot

Inkscape Copilot is a chat-first sidecar for Inkscape.

The current product surface is intentionally small:

1. Open an SVG in Inkscape.
2. Use `Extensions -> Copilot -> Open Copilot Chat`.
3. Talk to the copilot in the browser window.
4. When you send a message, the copilot plans the step and then applies it back into Inkscape.

The goal is simple: keep the assistant conversational, document-aware, and able to make supported edits directly on the current drawing.

## Inkscape Menu

The extension now exposes only two menu items:

- `Open Copilot Chat`
- `Apply Copilot Changes`

`Open Copilot Chat` opens a fresh browser-side chat window and captures a document snapshot from the current Inkscape file.

`Apply Copilot Changes` is the worker entry point that applies queued changes. In normal chat use, the browser triggers this automatically after action generation is done.

## Current Capabilities

The copilot can currently:

- modify the current selection
- create new basic shapes and diagram primitives
- create and edit text
- target existing objects by `object_id` or visible text
- replace text labels directly on existing drawings
- move or restyle existing objects without rebuilding the whole design
- use attached reference images in the chat flow when running on the OpenAI path

Supported action families include:

- selection style edits
- selection transforms
- object-targeted edits
- text replacement
- rectangle, rounded rectangle, circle, ellipse, polygon, star, line, arrow, bracket, repeated circles
- labeled layer bars for schematic diagrams

The copilot is conservative about page resizing:

- it will not change the page/canvas size unless you explicitly ask for it

## Product Behavior

The browser chat is the primary interface.

When you send a message:

1. the chat uses the latest synced document snapshot
2. the model replies briefly about what it will do
3. the model generates a structured action plan
4. the plan is queued
5. Inkscape is invoked once to apply the change

The chat UI is intentionally concise:

- assistant replies are short and operational
- the raw JSON action plan is not shown in the conversation
- the message area scrolls independently from the session panel

## Project Layout

- `inkscape_copilot/`: bridge, planner, executor, worker, web UI, and API bridge
- `inkscape_extension/`: Inkscape manifest files for the two remaining menu entries
- `state/`: runtime state used during local development
- `operation_flow.md`: current architecture and workflow notes

## Local Setup

Create one local `.env` file in the project root:

```bash
cp .env.example .env
```

Current recommended config:

```bash
INKSCAPE_COPILOT_PROVIDER=openai
MAIN_MODEL=gpt-5.4
OPENAI_API_KEY=your_openai_key_here
```

Optional variables:

- `OPENAI_BASE_URL`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `INKSCAPE_COPILOT_ENV_FILE`

The installed Inkscape extension is configured to read one root `.env` file. By default this project resolves:

```bash
/Users/xuetao.ma/Desktop/inkscape-copilot/.env
```

If you move the project somewhere else, point the extension at the correct file:

```bash
launchctl setenv INKSCAPE_COPILOT_ENV_FILE "/path/to/inkscape-copilot/.env"
```

## Python Environment

Create and install a local virtual environment:

```bash
cd /path/to/inkscape-copilot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Or use the included setup script:

```bash
cd /path/to/inkscape-copilot
bash scripts/setup_venv.sh
source .venv/bin/activate
```

Notes:

- `requirements.txt` installs the local package with `pip install -e .`
- the browser-side copilot does not need extra third-party API SDKs
- the Inkscape extension runtime uses Inkscape's bundled Python environment for `inkex`

## Run The Web UI Manually

From the project root:

```bash
source .venv/bin/activate
python3 -m inkscape_copilot.cli serve --port 8767
```

Then open:

```bash
http://127.0.0.1:8767
```

## Install Inkscape Extension

Copy into your Inkscape user extensions directory:

- the `inkscape_copilot/` package
- `inkscape_extension/inkscape_copilot_open_window.inx`
- `inkscape_extension/inkscape_copilot_apply_queue.inx`

On macOS this is typically:

```bash
~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions
```

After copying, restart Inkscape. The `Extensions -> Copilot` submenu should contain exactly:

- `Open Copilot Chat`
- `Apply Copilot Changes`

## Notes

- This is still an early product build.
- The architecture is now centered on a browser-side conversational UI plus an Inkscape-side executor.
- The next quality step is deeper SVG awareness and more reliable modification of existing compositions.

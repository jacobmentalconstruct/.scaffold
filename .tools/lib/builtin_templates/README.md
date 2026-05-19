# Project Name

> One-line description of what this project does.

## Quick Start

```bash
# Windows
setup_env.bat
run.bat

# Unix/Mac
chmod +x setup_env.sh run.sh
./setup_env.sh
./run.sh
```

## Architecture

See `_docs/reference/ARCHITECTURE.md` for the runtime model, file layout, and key design decisions.

## File Layout

```
project-root/
├── README.md, LICENSE.md, requirements.txt
├── setup_env.bat/.sh, run.bat/.sh
├── _docs/
│   ├── reference/ARCHITECTURE.md
│   ├── _journalDB/       (journal database)
│   └── _AppJOURNAL/      (journal config + exports)
├── .dev-tools/            (vendored agent tooling)
└── src/
    ├── app.py             (composition root)
    ├── core/
    │   ├── engine.py      (core orchestrator)
    │   └── ...            (domain modules)
    └── ui/
        ├── main_window.py (UI orchestrator)
        └── ...            (panes, widgets)
```

## License

See `LICENSE.md`.

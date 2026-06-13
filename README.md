# HTML to Elementor JSON Compiler

A production-grade CLI compiler that converts raw HTML pages (including Tailwind CSS and Bootstrap utility classes) into standard Elementor Pro JSON template files (v0.4 Schema) with ~95%+ visual layout fidelity. 

It is designed to bridge the structural and styling gaps between static web code and WordPress layouts, ensuring imported templates remain editable inside the Elementor builder.

---

## Key Features

- **Cascade CSS Parser**: A custom CSS engine that resolves rules based on CSS Specificity scoring (IDs, Classes, and Tags), handles CSS custom properties (`--variables`), evaluates `calc()` rules, and fetches remote stylesheets via `<link>` tags.
- **Utility Class Translators**: Extensive JIT compilers for Tailwind CSS (supporting arbitrary brackets like `w-[340px]`, `text-[#ff0000]`, and color opacity modifiers like `bg-red-500/30`) and Bootstrap 5 grid/spacing utilities.
- **Semantic Elementor Pro Widgets**: Automatically detects structure and converts native elements to Elementor Pro widgets (Forms, Sliders, Accordions, Tabs, Galleries, Stats/Counters, Testimonials, Icon Boxes, Navigation Menus, and Lists) instead of generic HTML blocks.
- **Custom CSS Injector**: Extracts pseudo-elements (`::before`, `::after`), state selectors (`:hover`, `:focus`), keyframe animations (`@keyframes`), and unsupported properties (e.g., `backdrop-filter`, `clip-path`) and maps them to Elementor's per-element or page-wide Custom CSS settings.
- **Automatic Asset Sync**: Post-processes and uploads local/remote images directly to WordPress via the WP REST API, replacing local paths with live media URLs and database attachment IDs in the template. Or, fallback to prepending a base URL locally.

---

## Project Structure

```text
├── compiler.py       # Main orchestrator, DOM tree traversal, & asset uploader
├── css_engine.py     # Specificity cascade parser, css vars, & pseudo extraction
├── tw_bs.py          # Tailwind JIT & Bootstrap utility class translators
├── widgets.py        # Pro widget heuristics & SVG/Icon library mapping
├── .gitignore        # Standard python / OS file exclusions
└── LICENSE           # MIT License
```

---

## Installation

1. Clone this repository:
   ```bash
   git clone <your-repo-url>
   cd elementor-to-html
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install beautifulsoup4
   ```

---

## Usage

Run the compiler using your input HTML file and the desired output path:

```bash
python3 compiler.py input.html output.json
```

### Advanced Arguments

- **`--base-asset-url`**: Prepends a target URL to all relative image, background, and video assets (useful for local offline compilation).
  ```bash
  python3 compiler.py input.html output.json --base-asset-url "https://mywebsite.com/wp-content/uploads/assets/"
  ```

- **`--wp-url`, `--wp-user`, `--wp-pass`**: Automatically upload all local assets to WordPress and update references in the template output.
  ```bash
  python3 compiler.py input.html output.json \
    --wp-url "https://mywebsite.com" \
    --wp-user "admin" \
    --wp-pass "abcd 1234 efgh 5678"
  ```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
Copyright (c) 2026 Rishabh Dev.

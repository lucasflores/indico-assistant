# Contract: Installation Section

## Section Requirements

**Location**: After Requirements section, before Configuration  
**Purpose**: Provide clear instructions for installing the plugin  
**Format**: Two installation methods with code examples

## Content Structure

### Main Header
```markdown
## Installation
```

---

### Method 1: PyPI Installation

```markdown
### From PyPI (Production)

```bash
pip install indico-plugin-assistant
```

**Note**: Requires access to PyPI and indico-plugin-assistant package publication.
```

**Verification**: Package name matches `pyproject.toml` [project] name field

---

### Method 2: Development Installation

```markdown
### From Source (Development)

```bash
# Clone repository
git clone https://github.com/your-org/indico-plugin-assistant.git
cd indico-plugin-assistant

# Install in editable mode
pip install -e ".[dev]"
```

**This installs**:
- Plugin in editable mode (changes reflected immediately)
- Development dependencies (pytest, ruff, black, mypy)
- All required dependencies from pyproject.toml
```

**Verification**: 
- Repository URL is correct (update with actual URL)
- Command format is standard Python package installation
- Dev dependencies referenced match `pyproject.toml` [dev]

---

### Post-Installation Steps

```markdown
### Enable the Plugin

After installation, enable the plugin in Indico:

1. Log in as administrator
2. Navigate to **Admin → Plugins**
3. Find "Assistant" plugin
4. Click **Enable**
5. Configure settings (see [Configuration](#configuration))

**Restart**: Indico may require restart after enabling plugin for first time.
```

**Verification**: Navigation path tested in Indico admin UI

---

## Content Requirements

1. **Clear distinction**: Production vs. development installation
2. **Commands are copy-pasteable**: No placeholder text in commands
3. **Prerequisites mentioned**: Reference Requirements section
4. **Post-install steps**: How to enable in Indico
5. **Links**: Cross-reference to Configuration section

## Verification Checklist

- [ ] Package name matches `pyproject.toml`
- [ ] Git repository URL is correct (or placeholder clearly marked)
- [ ] pip install commands are valid
- [ ] Editable mode syntax correct (`-e ".[dev]"`)
- [ ] Post-installation navigation path accurate
- [ ] Link to Configuration section works

## Optional: Docker Installation

```markdown
### Docker (Optional)

```bash
# Using official Indico Docker image
docker run -v /path/to/plugin:/opt/indico/plugins/assistant indico/indico
```

**Note**: Requires Indico Docker image. See Indico documentation for container setup.
```

**Include only if**: Official Docker support exists

---

## Success Criteria

- Users can install plugin successfully following instructions
- Both production and development paths are clear
- Post-installation steps guide users to next action
- No ambiguous placeholder text remains
- Commands work without modification

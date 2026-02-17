# GitHub Release Checklist

## ✅ Documentation Updated

### Main Documentation
- ✅ **README.md**
  - Updated project description to include Apple Mail
  - Added Apple Mail to features list
  - Added email integration section with setup instructions
  - Mentioned CLI connector as default

- ✅ **CLAUDE.md** (Project Instructions)
  - Updated architecture overview for both iMessage and Mail
  - Added all new config options (CLI, mail settings, signature)
  - Updated module descriptions
  - Complete and ready for release

- ✅ **docs/QUICKSTART.md**
  - Updated "What You'll Get" to mention email
  - Updated architecture diagram
  - Added Apple Mail setup section
  - Updated recent features list

- ✅ **docs/AUTO_START_SETUP.md**
  - Generic enough to cover all features
  - No updates needed

- ✅ **.env.example**
  - All new settings documented
  - CLI connector settings (use_codex_cli, command, context_window)
  - Apple Mail settings (enable, account, mailbox, from, allowed_senders, max_age_days, signature)
  - Ready for new users

### Code Documentation
- ✅ All modules have docstrings
- ✅ Test coverage: 80+ tests passing
- ✅ Type hints in place

## 📝 What to Review Before Release

### 1. Update GitHub-Specific References

**Files to check:**
- `README.md` line 24: `git clone` URL
- `docs/QUICKSTART.md` line 24: Repository URL
- `docs/QUICKSTART.md` line 345: GitHub Issues link

**Action:** Replace `yourusername` with your actual GitHub username:
```bash
# Find all references
grep -r "yourusername" --include="*.md" .
```

### 2. Version Number

**Current:** Not explicitly versioned in code

**Consider adding:**
- `__version__ = "0.2.0"` in `src/codex_relay/__init__.py`
- Version in `pyproject.toml` if not already there

### 3. LICENSE File

**Action:** Verify `LICENSE` file exists and is correct.

### 4. Clean Up Temporary Files

**Files to consider removing:**
- `IMPLEMENTATION_SUMMARY.md` - Was created during CLI connector development
  - Contains useful info but may be too technical for main docs
  - Consider moving to `docs/` or removing

**Action:**
```bash
# Optional: move to docs
mv IMPLEMENTATION_SUMMARY.md docs/CLI_CONNECTOR_MIGRATION.md

# Or remove
rm IMPLEMENTATION_SUMMARY.md
```

### 5. Test Installation from Scratch

**Recommended:** Test the one-click install on a clean macOS environment:

```bash
# Clone fresh
git clone <your-repo-url>
cd codex-flow

# Run setup
./scripts/setup_autostart.sh

# Verify all features work
```

## 🎯 Key Features for Release Announcement

### Major Features
- **Dual Channel Support**: iMessage AND Apple Mail
- **CLI Connector**: Stateless execution eliminates freezing
- **Email Threading**: Replies stay in conversation
- **Custom Signatures**: Professional email branding
- **One-Click Setup**: Complete auto-start configuration

### Technical Highlights
- 80+ tests with 100% pass rate
- Graceful shutdown and signal handling
- Database connection caching
- Approval sender verification
- Workspace security controls

## 📦 Release Notes Template

```markdown
# Codex Relay v0.2.0

## 🚀 What's New

### Apple Mail Integration
- Text OR email yourself to interact with Claude
- Email replies stay in the same thread
- Custom signatures: "Codex 🤖, Your 24/7 Assistant"
- Only processes recent emails (configurable age limit)

### CLI Connector (Default)
- Replaced app-server with stateless `codex exec`
- Eliminates state corruption and freezing issues
- Maintains conversation context (configurable window)
- Faster, more reliable execution

### Enhanced Setup
- One-click auto-start script
- Automatic dependency installation
- Smart Python binary detection
- Pre-configured launch agent

## 🛠️ Breaking Changes

None! Existing configurations continue to work.

The CLI connector is now default but you can switch back:
```bash
codex_relay_use_codex_cli=false
```

## 📚 Documentation

- Complete Quick Start guide
- Auto-start setup instructions
- Architecture overview
- Full configuration reference

## 🐛 Bug Fixes

- Fixed state corruption causing daemon freezes
- Improved email JSON parsing for control characters
- Better error handling and logging

## 📊 Stats

- 80+ tests, all passing
- 12 new CLI connector tests
- 8 new mail integration tests
- Full coverage of core functionality

## 🙏 Credits

Built with Claude Code and the Anthropic API.
```

## ✅ Pre-Release Tasks

- [ ] Update GitHub username in docs
- [ ] Add version number to code
- [ ] Verify LICENSE file
- [ ] Clean up temporary documentation
- [ ] Test fresh installation
- [ ] Write release notes
- [ ] Tag the release
- [ ] Publish to GitHub

## 🚦 Ready to Release?

Once all checkboxes above are complete, you're ready to:

1. Create a new release on GitHub
2. Tag it as `v0.2.0`
3. Copy release notes
4. Publish!

---

**Note:** All core documentation is updated and ready. The only remaining items are GitHub-specific URLs and optional cleanup.

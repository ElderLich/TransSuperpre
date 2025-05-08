# 🃏 Pre-Release Cards Tutorial by Senator John

Want to translate your favorite or the latest announced cards for MDPro3 Super-Pre? No worries — Senator John has you covered with this short tutorial and toolset!

## 🛠️ Tools Needed

Make sure to install the following before starting:

- [Python](https://www.python.org/downloads/)
- This translation [Tool](https://pixeldrain.com/u/nJAY2xYA) (credits to @Reinen of The Wire Forest)
- [DataEditorX](https://github.com/Lyris12/DataEditorX/releases/download/omega/win64.zip)
- [SQLite (alternative solid editor)](https://sqlitebrowser.org/dl/)
- [GitHub](https://github.com/) Account
- [GitHub Desktop](https://desktop.github.com/)

## 🌐 Translation Resources

 **Primary Source (Chinese):** [SuperPre](https://mycard.world/ygopro/arena/index.html#/superpre)
- **Primary Source (English):** [YGOrganization](https://ygorganization.com/)
- **French Source:** [YugiNews](https://yuginews.fr/)
  
> ⚠️ Note: When translating into other languages, **do not reuse the OCG card numbering from the English version** — it causes issues during merge with the main `.cdb` file.

---

## 🚀 Getting Started

### 1. Download the Latest Files
When new cards are announced, the `super-pre.ypk` file will be updated. You need to download it from the provided link.

### 2. Unpack the Files
Use WinZip or WinRAR to extract `ygopro-super-pre.ypk`. Set up your folders:
- Folder A: Your working language (e.g. `FR`)
- Folder B: Extracted raw files from `super-pre.ypk` (e.g. `CN`)

### 3. Files to Focus On
Once unpacked, you’ll find three important files:

- `test-update.cdb` – contains older cards updated to new archetypes
- `test-strings.conf` – names of new archetypes
- `test-release.cdb` – latest cards added to the pool

---

## 📝 Translation Workflow

1. Open `test-release.cdb` in **DataEditorX**
2. Translate:
   - Card Names
   - Card Effects
   - Card Strings (effect prompts shown in-game)
3. Click `Modify` to save your changes.

💡 *You can also compare two `.cdb` files to check for missing cards. Zero results means both databases are synced.*

---

## 📦 Preparing for Repackaging

Once your translations are done:

1. Replace the edited files in the original `ygopro-super-pre.ypk`.
2. Download the translation packaging tool (Python script).
3. Place the script in the same folder as `test-release.cdb`.

### Setup Python Environment

```bash
pip install requests
```

Run the script by double-clicking or using the command line.

> 📝 If translating to a language other than English, update the language files **inside the script** accordingly.

### Output Files

- `test-release.json` – Required for YGOmobile
- `version.txt` – Contains UNIX timestamp to signal a new version to the game

---

## ☁️ Uploading to GitHub

1. Clone Senator John’s repo using [GitHub Desktop](https://desktop.github.com/) or Git CLI.
2. Navigate to the appropriate language folder (e.g. `FR/` for French).
3. Paste your updated files.
4. Use **GitHub Desktop** to commit and push your changes.

> 📤 Each language should have its own folder. For example, French goes in `FR/`.


---

## 🙌 Credits

- Tool by **@Reinen** of *The Wire Forest*
- Project led and documented by **Senator John**

---

Happy translating! 🇺🇳

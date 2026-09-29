# Windows setup

## 1. Install Git and VS Code (one time)

Open **PowerShell** from the Start menu and run:

```powershell
winget install --id Git.Git -e; winget install --id Microsoft.VisualStudioCode -e
```

Close PowerShell when it finishes.

## 2. Download the project (one time)

Open a new PowerShell window and run:

```powershell
cd $HOME\Documents
git clone https://github.com/nathanwinklepleck/ben-sullivan-real-estate.git
```

A browser window will ask you to sign in to GitHub. Use the account that was invited to the repo.

## 3. Install everything else (one time)

Open `Documents\ben-sullivan-real-estate` in File Explorer and double-click **setup.bat**. It installs Python, Node.js, and the PDF libraries, and then runs the tests. Approve any Windows permission prompts. Wait for "Setup complete". If a step fails, you can run it again safely.

## 4. Run the app

Double-click **start.bat**. Two command windows will open (keep them open), and then the app will open in your browser at http://127.0.0.1:5173. To stop the app, close both command windows.

### Using VS Code instead

Open VS Code, choose **File > Open Folder**, and select the project folder. Click **Install** if VS Code suggests extensions. Press **Ctrl+Shift+B** to start the app. To run the tests, open **Terminal > Run Task...** and choose **Run tests**.

## Getting updates

In PowerShell, from the project folder:

```powershell
git pull
```

Or, in VS Code, click the Source Control icon on the left and then **Sync Changes**. Run setup.bat again after any update that changes dependencies.

Saved deals are stored in `data\deals.sqlite3`, and that file is tracked in git. If you save deals and we both change that file, `git pull` will report a conflict. Ask before you commit changes to it.

## Troubleshooting

- **"winget is not recognized"**: install **App Installer** from the Microsoft Store.
- **PDF export fails with a missing library or `cannot load library` error**: run setup.bat again. PDF export needs `C:\msys64\mingw64\bin`.
- **"Port 8000/5173 is already in use"**: close any old app windows, or restart the computer.

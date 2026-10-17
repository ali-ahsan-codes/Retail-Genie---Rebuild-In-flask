# Deployment Setup Guide

This document explains how to prepare a fresh Windows machine to run **Retail Genie** using the one-click silent launcher.

## 1. Prerequisites

### Node.js
The application requires Node.js to run the server.
- **Download:** [https://nodejs.org/](https://nodejs.org/)
- **Version:** Latest LTS (Long Term Support) is recommended.
- **Installation:** Run the installer and keep all default settings (especially "Add to PATH").

### Terminal / PowerShell
Windows 10 and 11 come with PowerShell pre-installed. The installer uses a `.ps1` script to automate the process.

## 2. Windows Configuration

By default, Windows prevents PowerShell scripts from running. You must enable them once per computer:

1. Click **Start** and type `PowerShell`.
2. Right-click **Windows PowerShell** and select **Run as Administrator**.
3. Paste the following command and press **Enter**:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
4. Type `Y` and press **Enter** to confirm.

## 3. Using the One-Click Launcher

Once Node.js is installed and the execution policy is set:

1. Copy the project folder to the target computer.
2. Locate `launcher.vbs` in the root of the project folder.
3. **Double-click `launcher.vbs`**.

### What happens next?
- **No window will appear.** The process runs entirely in the background.
- The script will:
  - Install dependencies (`npm install`).
  - Build the production application (`npm run build`).
  - Clean up the directory by **deleting original source code** (IP protection).
  - Start the web server silently.
- The process takes **2-5 minutes** depending on the computer speed.

## 4. Manual Run (Visible Progress)
If you prefer to see what is happening or need to debug:
1. Right-click `install-and-start.ps1`.
2. Select **Run with PowerShell**.
3. Keep the window open until it finishes.

## 5. Accessing the Application

After a few minutes, the app will be available at:
**[http://localhost:3000](http://localhost:3000)**

- **Default Credentials:**
  - **Username:** `admin`
  - **Password:** `password123`

## 6. Troubleshooting

- **App doesn't load:** Check if `node.exe` is running in the Task Manager.
- **Port Conflict:** Ensure no other app is using port 3000.
- **Source Deletion:** Remember that the script deletes the `src/` folder after building to protect your code. Keep a backup of the source code elsewhere!

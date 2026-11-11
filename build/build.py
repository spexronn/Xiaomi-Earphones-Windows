"""SPEXRON Buds Monitor — Windows EXE derleme betiği.

Kullanım (proje kökünden):
    .venv\\Scripts\\python.exe build\\build.py

Çıktı: dist\\SPEXRON Buds Monitor\\SPEXRON Buds Monitor.exe  (onedir, taşınabilir klasör)
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.paths import APP_NAME, APP_VERSION, DEVELOPER  # noqa: E402


def make_icon(path: Path) -> None:
    """Uygulama simgesini QPainter ile çizip çok çözünürlüklü PNG-ICO olarak yazar."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    from ui.graphics import app_icon
    icon = app_icon()
    sizes = (16, 24, 32, 48, 64, 128, 256)
    blobs = []
    for s in sizes:
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        icon.pixmap(s, s).save(buf, "PNG")
        blobs.append(ba.data())
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, data = b"", b""
    for s, b in zip(sizes, blobs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), offset + len(data))
        data += b
    path.write_bytes(header + entries + data)
    # README ve arayüz için PNG
    icon.pixmap(256, 256).save(str(path.with_suffix(".png")), "PNG")


def make_version_file(path: Path) -> None:
    v = tuple(int(x) for x in APP_VERSION.split(".")) + (0,)
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041F04B0', [
      StringStruct('CompanyName', '{DEVELOPER}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{APP_VERSION}'),
      StringStruct('InternalName', 'SPEXRON Buds App'),
      StringStruct('LegalCopyright', '© {DEVELOPER}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', 'SPEXRON Buds App'),
      StringStruct('ProductVersion', '{APP_VERSION}')])]),
    VarFileInfo([VarStruct('Translation', [0x041F, 1200])])
  ]
)
""", encoding="utf-8")


def make_root_launcher(root: Path, app_name: str, ico: Path) -> None:
    """Ana dizinde çift tıklandığında dist içindeki uygulamayı başlatan EXE ve kısayol üretir."""
    # 1. Kısayol (.lnk)
    try:
        lnk_path = root / f"{app_name}.lnk"
        target_path = root / "dist" / app_name / f"{app_name}.exe"
        work_dir = root / "dist" / app_name
        ps_cmd = (
            f"$s = (New-Object -COM WScript.Shell).CreateShortcut('{lnk_path}');"
            f"$s.TargetPath = '{target_path}';"
            f"$s.WorkingDirectory = '{work_dir}';"
            f"$s.IconLocation = '{ico}';"
            f"$s.Save()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True)
    except Exception:
        pass

    # 2. Ana dizin başlatıcı EXE (Windows csc.exe ile yerel C# derlemesi)
    windir = os.environ.get("WINDIR", r"C:\Windows")
    csc = Path(windir) / r"Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if not csc.exists():
        csc = Path(windir) / r"Microsoft.NET\Framework\v4.0.30319\csc.exe"

    out_exe = root / f"{app_name}.exe"
    if not csc.exists():
        import shutil
        shutil.copy2(root / "dist" / app_name / f"{app_name}.exe", out_exe)
        return

    cs_code = f"""using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("{app_name}")]
[assembly: AssemblyDescription("{app_name}")]
[assembly: AssemblyCompany("{DEVELOPER}")]
[assembly: AssemblyProduct("{app_name}")]
[assembly: AssemblyCopyright("© {DEVELOPER}")]
[assembly: AssemblyVersion("{APP_VERSION}.0")]
[assembly: AssemblyFileVersion("{APP_VERSION}.0")]

static class Program {{
    [STAThread]
    static int Main(string[] args) {{
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string exe = Path.Combine(root, "dist", "{app_name}", "{app_name}.exe");
        if (!File.Exists(exe)) {{
            MessageBox.Show(
                "Derlenmiş uygulama bulunamadı:\\n" + exe + "\\n\\nLütfen önce build.bat ile derleme yapın.",
                "{app_name}", MessageBoxButtons.OK, MessageBoxIcon.Warning
            );
            return 1;
        }}

        string cmdArgs = "";
        if (args != null && args.Length > 0) {{
            cmdArgs = string.Join(" ", Array.ConvertAll(args, a => a.Contains(" ") ? "\\"" + a + "\\"" : a));
        }}

        var psi = new ProcessStartInfo {{
            FileName = exe,
            Arguments = cmdArgs,
            WorkingDirectory = Path.GetDirectoryName(exe),
            UseShellExecute = false
        }};

        try {{
            var p = Process.Start(psi);
            if (p == null) return 1;
            bool wait = args != null && (Array.IndexOf(args, "--stop") >= 0 || Array.IndexOf(args, "--diagnose") >= 0);
            if (wait) {{
                p.WaitForExit();
                return p.ExitCode;
            }}
            return 0;
        }} catch (Exception ex) {{
            MessageBox.Show("Başlatılamadı: " + ex.Message, "Hata", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }}
    }}
}}
"""
    cs_file = root / "build" / "work" / "launcher.cs"
    cs_file.write_text(cs_code, encoding="utf-8")
    cmd = [
        str(csc),
        "/nologo",
        "/target:winexe",
        f"/win32icon:{ico}",
        f"/out:{out_exe}",
        str(cs_file),
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        import shutil
        shutil.copy2(root / "dist" / app_name / f"{app_name}.exe", out_exe)


def main() -> int:
    # Çıktı dosyaya yönlendirildiğinde Windows cp1254 kullanır; Türkçe/özel karakterlerde çökmesin
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    ico = assets / "icon.ico"
    make_icon(ico)
    work = ROOT / "build" / "work"
    work.mkdir(parents=True, exist_ok=True)
    ver = work / "version_info.txt"
    make_version_file(ver)

    cmd = [
        sys.executable, "-m", "PyInstaller", str(ROOT / "main.py"),
        "--name", APP_NAME,
        "--onedir",            # tek dosya yerine klasör: her açılışta geçici klasöre açma yok → hızlı başlar
        "--windowed",
        "--noconfirm", "--clean",
        "--icon", str(ico),
        "--version-file", str(ver),
        "--add-data", f"{assets};assets",
        "--collect-submodules", "winrt",
        "--exclude-module", "tkinter",
        "--exclude-module", "bleak",
        "--exclude-module", "pytest",
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(work),
        "--specpath", str(work),
    ]
    print(" ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode == 0:
        out = ROOT / "dist" / APP_NAME
        (out / "portable.flag").write_text(
            "Bu dosya varsa ayarlar ve loglar EXE'nin yanındaki config/ ve logs/ klasörlerine yazılır.\n"
            "Silerseniz %LOCALAPPDATA%\\SPEXRON\\BudsMonitor kullanılır.\n", encoding="utf-8")
        make_root_launcher(ROOT, APP_NAME, ico)
        print(f"\nTAMAM (Ana Dizin): {ROOT / (APP_NAME + '.exe')}")
        print(f"TAMAM (Dağıtım)  : {out / (APP_NAME + '.exe')}")
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())

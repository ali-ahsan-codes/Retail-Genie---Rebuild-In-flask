import os
import subprocess
import json
import zipfile
import shutil
import tempfile
import re
from datetime import datetime
from flask import current_app, has_app_context
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# ------------------------------------------------------------
# Configuration helpers (mix of config.json & .env)
# ------------------------------------------------------------

def get_config():
    """Load config.json from the same directory."""
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)

def get_backup_dir():
    """Return backup folder from config.json or default."""
    config = get_config()
    return config.get('app', {}).get('backup_folder', './backups')

def get_max_backups():
    """Return maximum number of backups to keep from config.json or default."""
    config = get_config()
    return int(config.get('app', {}).get('max_backups', 100))

def get_backup_interval():
    """Return backup interval in minutes from config.json or default."""
    config = get_config()
    return int(config.get('app', {}).get('backup_interval_minutes', 5))

def get_mysql_credentials():
    """Parse DATABASE_URL from .env and return credentials dict."""
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL not set in .env")
    # Remove scheme
    db_url = db_url.replace('mysql+pymysql://', '')
    # user:pass@host:port/db
    match = re.match(r'([^:]+):([^@]+)@([^:]+):(\d+)/(.+)', db_url)
    if not match:
        raise ValueError("Invalid DATABASE_URL format")
    user, password, host, port, database = match.groups()
    # URL-decode password (if it contains %40 for @ etc.)
    password = password.replace('%40', '@')
    return {
        'user': user,
        'password': password,
        'host': host,
        'port': int(port),
        'database': database
    }

def get_timestamp():
    now = datetime.now()
    return now.strftime('%Y-%m-%d_%H-%M-%S') + f'-{now.microsecond:06d}'

def find_mysql_executable(exe_name):
    """Locate mysql or mysqldump executable."""
    path = shutil.which(exe_name)
    if path:
        return path
    # Common installation paths for Windows
    common_paths = [
        os.environ.get('ProgramFiles', 'C:\\Program Files') + f'\\MySQL\\MySQL Server 8.0\\bin\\{exe_name}.exe',
        os.environ.get('ProgramFiles', 'C:\\Program Files') + f'\\MySQL\\MySQL Server 5.7\\bin\\{exe_name}.exe',
        os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)') + f'\\MySQL\\MySQL Server 8.0\\bin\\{exe_name}.exe',
        os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)') + f'\\MySQL\\MySQL Server 5.7\\bin\\{exe_name}.exe',
        'C:\\Program Files\\MySQL\\MySQL Server 8.0\\bin\\' + exe_name + '.exe',
        'C:\\Program Files (x86)\\MySQL\\MySQL Server 8.0\\bin\\' + exe_name + '.exe',
    ]
    for path in common_paths:
        if os.path.isfile(path):
            return path
    return None

def create_mysql_option_file(creds):
    """Create temporary option file for mysql client."""
    fd, path = tempfile.mkstemp(suffix='.cnf', text=True)
    with os.fdopen(fd, 'w') as f:
        f.write(f"[client]\nuser={creds['user']}\npassword={creds['password']}\nhost={creds['host']}\nport={creds['port']}\n")
    return path

# ------------------------------------------------------------
# Backup metadata management (JSON)
# ------------------------------------------------------------

def get_meta_path():
    backup_dir = get_backup_dir()
    return os.path.join(backup_dir, 'backup_meta.json')

def load_meta():
    meta_path = get_meta_path()
    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            return json.load(f)
    return None

def save_meta(meta):
    meta_path = get_meta_path()
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

def cleanup_backups(meta=None):
    """
    Reconcile the meta file with the actual file system.
    - Remove entries where the folder no longer exists.
    - Remove entries beyond max_backups (oldest first).
    - Delete orphaned folders that are not in meta.
    """
    backup_dir = get_backup_dir()
    os.makedirs(backup_dir, exist_ok=True)

    if meta is None:
        meta = load_meta()
    if meta is None:
        meta = {'version': 2, 'next_id': 1, 'backups': []}
        save_meta(meta)
        return meta

    # 1. Remove entries whose folder is missing
    valid_entries = []
    for entry in meta['backups']:
        folder = os.path.dirname(entry['sql_file'])
        if os.path.exists(folder):
            valid_entries.append(entry)
    meta['backups'] = valid_entries

    # 2. Sort by id (oldest first)
    meta['backups'].sort(key=lambda b: b['id'])

    # 3. Trim to max_backups
    max_backups = get_max_backups()
    if len(meta['backups']) > max_backups:
        to_remove = meta['backups'][:-max_backups]
        for entry in to_remove:
            folder = os.path.dirname(entry['sql_file'])
            if os.path.exists(folder):
                shutil.rmtree(folder)
        meta['backups'] = meta['backups'][-max_backups:]

    # 4. Remove orphaned folders (folders named backup_* that are not in meta)
    existing_folders = [f for f in os.listdir(backup_dir) if f.startswith('backup_') and os.path.isdir(os.path.join(backup_dir, f))]
    meta_ids = set(os.path.basename(os.path.dirname(entry['sql_file'])) for entry in meta['backups'])
    for folder in existing_folders:
        if folder not in meta_ids:
            shutil.rmtree(os.path.join(backup_dir, folder))

    # 5. Update next_id if it's less than max(id)+1
    if meta['backups']:
        max_id = max(entry['id'] for entry in meta['backups'])
        if meta['next_id'] <= max_id:
            meta['next_id'] = max_id + 1
    else:
        meta['next_id'] = 1

    save_meta(meta)
    return meta

def migrate_legacy_backups():
    """
    If no meta file exists, scan the backup root for .sql files
    and create meta entries for them, moving each into a backup_<id> folder.
    """
    meta = load_meta()
    if meta is not None:
        return meta

    backup_dir = get_backup_dir()
    os.makedirs(backup_dir, exist_ok=True)

    sql_files = [f for f in os.listdir(backup_dir) if f.startswith('gyropulse_') and f.endswith('.sql')]
    if not sql_files:
        meta = {'version': 2, 'next_id': 1, 'backups': []}
        save_meta(meta)
        return meta

    sql_files.sort()
    meta = {'version': 2, 'next_id': 1, 'backups': []}

    for idx, filename in enumerate(sql_files):
        src_path = os.path.join(backup_dir, filename)
        try:
            ts_str = filename.replace('gyropulse_', '').replace('.sql', '')
            ts = datetime.strptime(ts_str, '%Y-%m-%d_%H-%M-%S-%f')
        except:
            ts = datetime.fromtimestamp(os.path.getmtime(src_path))

        backup_id = meta['next_id']
        meta['next_id'] += 1

        folder_name = f"backup_{backup_id:04d}"
        folder_path = os.path.join(backup_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)

        new_sql_path = os.path.join(folder_path, 'dump.sql')
        shutil.move(src_path, new_sql_path)

        zip_file = filename.replace('.sql', '.zip')
        zip_src = os.path.join(backup_dir, zip_file)
        zip_dst = os.path.join(folder_path, 'backup.zip')
        if os.path.exists(zip_src):
            shutil.move(zip_src, zip_dst)

        meta['backups'].append({
            'id': backup_id,
            'timestamp': ts.isoformat(),
            'sql_file': new_sql_path,
            'zip_file': zip_dst if os.path.exists(zip_dst) else None,
            'status': 'completed'
        })

    save_meta(meta)
    return meta

# ------------------------------------------------------------
# Core backup creation
# ------------------------------------------------------------

def create_backup():
    """
    Creates a new backup using the folder-per-backup structure,
    updates meta, and rotates old backups if necessary.
    Returns the backup ID and folder path.
    """
    creds = get_mysql_credentials()
    backup_dir = get_backup_dir()
    os.makedirs(backup_dir, exist_ok=True)

    # Ensure meta exists and clean up any orphaned items
    meta = migrate_legacy_backups()
    # Run cleanup to ensure we are within limits and consistent
    meta = cleanup_backups()

    # Get next ID
    backup_id = meta['next_id']
    meta['next_id'] += 1

    # Create folder
    folder_name = f"backup_{backup_id:04d}"
    folder_path = os.path.join(backup_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    sql_file = os.path.join(folder_path, 'dump.sql')
    timestamp = datetime.utcnow()

    mysqldump = find_mysql_executable('mysqldump')
    if not mysqldump:
        raise Exception("mysqldump not found. Please install MySQL client tools.")

    opt_file = create_mysql_option_file(creds)
    try:
        cmd = [
            mysqldump,
            f'--defaults-extra-file={opt_file}',
            '--single-transaction',
            '--routines',
            '--triggers',
            creds['database']
        ]
        with open(sql_file, 'w', encoding='utf-8') as f:
            result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise Exception(f"Backup failed: {result.stderr.decode()}")
    finally:
        if os.path.exists(opt_file):
            os.remove(opt_file)

    # Add entry to meta
    meta['backups'].append({
        'id': backup_id,
        'timestamp': timestamp.isoformat(),
        'sql_file': sql_file,
        'zip_file': None,
        'status': 'completed'
    })

    # Save updated meta and clean up / rotate old backups
    save_meta(meta)
    meta = cleanup_backups(meta)

    return backup_id, folder_path

# ------------------------------------------------------------
# Backup & restore functions (public API)
# ------------------------------------------------------------

def backup_db():
    """
    Public wrapper for scheduled backup. Creates a new backup and returns the SQL file path.
    """
    backup_id, folder_path = create_backup()
    sql_file = os.path.join(folder_path, 'dump.sql')
    return sql_file

def list_backup_files():
    """
    Returns a list of backup IDs with metadata (for UI).
    """
    meta = migrate_legacy_backups()
    backups = sorted(meta['backups'], key=lambda b: b['id'], reverse=True)
    result = []
    for b in backups:
        result.append({
            'id': b['id'],
            'timestamp': b['timestamp'],
            'sql_file': b['sql_file'],
            'zip_file': b.get('zip_file')
        })
    return result

def export_backup_zip(backup_id=None):
    """
    Creates a ZIP archive of a backup folder. If backup_id is None, uses the latest.
    Returns the path to the ZIP file.
    """
    meta = migrate_legacy_backups()
    if not meta['backups']:
        create_backup()
        meta = migrate_legacy_backups()

    if backup_id is None:
        latest = max(meta['backups'], key=lambda b: b['id'])
    else:
        latest = next((b for b in meta['backups'] if b['id'] == backup_id), None)
        if not latest:
            raise ValueError(f"Backup with id {backup_id} not found")

    folder = os.path.dirname(latest['sql_file'])
    zip_path = os.path.join(folder, 'backup.zip')
    if os.path.exists(zip_path):
        return zip_path

    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(latest['sql_file'], 'dump.sql')
        if has_app_context():
            media_path = current_app.config.get('UPLOAD_FOLDER', './uploads')
        else:
            media_path = get_config().get('app', {}).get('upload_folder', './uploads')

        # Include media upload files in the ZIP archive
        if os.path.exists(media_path) and os.path.isdir(media_path):
            for root, _, files in os.walk(media_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, media_path)
                    arc_path = os.path.join('uploads', rel_path)
                    zipf.write(full_path, arc_path)

        manifest = {
            'media_path': media_path,
            'backup_time': datetime.now().isoformat(),
            'database': get_mysql_credentials()['database'],
            'backup_id': latest['id']
        }
        manifest_path = os.path.join(folder, 'manifest.json')
        with open(manifest_path, 'w') as mf:
            json.dump(manifest, mf)
        zipf.write(manifest_path, 'manifest.json')
        os.remove(manifest_path)

    latest['zip_file'] = zip_path
    save_meta(meta)
    return zip_path

def import_backup_from_zip(zip_file, mode='flush', new_media_path=None):
    """
    Import a backup from a ZIP file.
    """
    if hasattr(zip_file, 'read'):
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            zip_file.save(tmp.name)
            zip_path = tmp.name
    else:
        zip_path = zip_file

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(tmpdir)
            sql_files = [f for f in os.listdir(tmpdir) if f.endswith('.sql')]
            if not sql_files:
                raise Exception("No SQL file found in zip")
            sql_path = os.path.join(tmpdir, sql_files[0])
            restore_database_from_sql(sql_path, mode)

            # Restore media files if present in zip
            media_dir_in_zip = os.path.join(tmpdir, 'uploads')
            if os.path.exists(media_dir_in_zip) and os.path.isdir(media_dir_in_zip):
                target_media_path = new_media_path or get_config().get('app', {}).get('upload_folder', './uploads')
                os.makedirs(target_media_path, exist_ok=True)
                for root, _, files in os.walk(media_dir_in_zip):
                    for file in files:
                        src_file = os.path.join(root, file)
                        rel_path = os.path.relpath(src_file, media_dir_in_zip)
                        dst_file = os.path.join(target_media_path, rel_path)
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
            elif new_media_path:
                update_media_path_in_config(new_media_path)
    finally:
        if hasattr(zip_file, 'read') and os.path.exists(zip_path):
            os.remove(zip_path)

def restore_database_from_sql(sql_file_path, mode='flush'):
    """
    Restore database from SQL file.
    """
    creds = get_mysql_credentials()
    if mode == 'flush':
        mysql = find_mysql_executable('mysql')
        if not mysql:
            raise Exception("mysql executable not found. Please ensure MySQL client is installed.")
        opt_file = create_mysql_option_file(creds)
        try:
            cmd = [mysql, f'--defaults-extra-file={opt_file}', creds['database']]
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                result = subprocess.run(cmd, stdin=f, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    raise Exception(f"Import failed: {result.stderr.decode()}")
        finally:
            if os.path.exists(opt_file):
                os.remove(opt_file)
    else:
        engine = create_engine(
            f"mysql+pymysql://{creds['user']}:{creds['password']}@{creds['host']}:{creds['port']}/{creds['database']}"
        )
        with engine.connect() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            with open(sql_file_path, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            pattern = re.compile(r'INSERT\s+INTO\s+`?(\w+)`?\s+VALUES\s*\((.+?)\);', re.IGNORECASE | re.DOTALL)
            matches = pattern.findall(sql_content)
            for table, values in matches:
                insert_sql = f"INSERT IGNORE INTO `{table}` VALUES ({values});"
                try:
                    conn.execute(text(insert_sql))
                except Exception as e:
                    print(f"Error inserting into {table}: {e}")
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
            conn.commit()

def update_media_path_in_config(new_path):
    """
    Update the media path in config (legacy function).
    """
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r') as f:
        config = json.load(f)
    config['app']['upload_folder'] = new_path
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

# ------------------------------------------------------------
# Legacy rotation (kept for compatibility)
# ------------------------------------------------------------

def rotate_backups(backup_dir, keep=100):
    pass
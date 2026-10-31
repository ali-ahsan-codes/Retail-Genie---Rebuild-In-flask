import os
import json
import base64
import uuid
import secrets
import hashlib
import sqlite3
import tempfile
import random
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, Tuple, Any

from werkzeug.utils import secure_filename
from flask import current_app, has_request_context, request

# Cryptography imports
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# Import models globally to avoid NameError
from models import db, User, ApiKey, TokenPool, Product, Inventory, Warehouse, DeviceCommand, Media

# ==================================================================
# LEGACY UTILITY FUNCTIONS (preserved)
# ==================================================================

def generate_api_key():
    """Generate a random UUID hex string for legacy role API keys."""
    return uuid.uuid4().hex

def save_uploaded_file(file, subfolder=''):
    """Save an uploaded file to the configured upload folder."""
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    unique = f"{datetime.utcnow().timestamp()}_{filename}"
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, unique)
    file.save(path)
    return f"/uploads/{subfolder}/{unique}" if subfolder else f"/uploads/{unique}"

def save_multiple_files(files, subfolder=''):
    """Save multiple uploaded files and return list of (media_type, url)."""
    uploaded = []
    for file in files:
        if not file or not file.filename:
            continue
        filename = file.filename.lower()
        if filename.endswith(('.mp4', '.mov', '.webm', '.3gp')):
            media_type = 'video'
        elif filename.endswith(('.mp3', '.wav', '.aac', '.m4a')):
            media_type = 'audio'
        elif filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            media_type = 'image'
        else:
            media_type = 'attachment'

        url = save_uploaded_file(file, subfolder)
        if url:
            uploaded.append((media_type, url))
    return uploaded

# ==================================================================
# CRYPTOGRAPHIC HELPERS (AES-256 + PBKDF2)
# ==================================================================

def get_master_secret() -> bytes:
    """
    Retrieve the system-wide master secret from environment or config.
    This must be set in .env as MASTER_SECRET (64 hex chars).
    If not set, a warning is logged and a temporary fallback is used (not for production).
    """
    master = (os.environ.get('MASTER_SECRET') or '').strip()
    placeholder_values = {
        '',
        'replace_with_your_64_char_hex_key_here',
        'your-master-secret-here-64-hex-chars'
    }
    if not master or master in placeholder_values:
        master = current_app.config.get('SECRET_KEY', os.environ.get('SECRET_KEY', 'gyropulse-master-secret'))
        current_app.logger.warning('MASTER_SECRET not set or placeholder detected; using app secret as fallback.')
    return master.encode('utf-8')

def derive_key_from_password(password: bytes, salt: bytes, length: int = 32) -> bytes:
    """Derive a 32-byte key using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return kdf.derive(password)

def aes_encrypt(plaintext: bytes, key: bytes, iv: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """
    Encrypt plaintext using AES-256-CBC with PKCS7 padding.
    Returns (ciphertext, iv). If iv is None, a random IV is generated.
    """
    if len(key) != 32:
        raise ValueError('Key must be 32 bytes for AES-256.')
    if iv is None:
        iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext) + padder.finalize()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return ciphertext, iv

def aes_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """Decrypt AES-256-CBC with PKCS7 padding."""
    if len(key) != 32:
        raise ValueError('Key must be 32 bytes for AES-256.')
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded) + unpadder.finalize()
    return plaintext

def build_gpc_payload(user, api_key: str, session_id: str, device_uuid: str, expiry_date, catalog: dict,
                     tokens: List[str], show_stock: bool = True, base_url: Optional[str] = None,
                     master_secret: Optional[str] = None) -> dict:
    """Build the Android-compatible payload contract for .gpc login files."""
    final_base_url = (base_url or current_app.config.get('BASE_URL') or current_app.config.get('SERVER_URL') or '').strip()
    if not final_base_url:
        final_base_url = 'http://localhost:5000/'
    if not final_base_url.startswith(('http://', 'https://')):
        final_base_url = 'http://' + final_base_url
    if not final_base_url.endswith('/'):
        final_base_url += '/'

    secret_value = (master_secret or get_master_secret().decode('utf-8'))
    payload = {
        'user_id': getattr(user, 'id', None),
        'username': getattr(user, 'username', None),
        'api_key': api_key,
        'session_id': session_id,
        'device_uuid': device_uuid,
        'base_url': final_base_url,
        'server_url': final_base_url,
        'expiry_date': expiry_date.isoformat() if hasattr(expiry_date, 'isoformat') else str(expiry_date),
        'catalog_permissions': {'show_stock_quantity': bool(show_stock)},
        'tokens': tokens,
        'catalog': catalog,
        'role': getattr(user, 'role', None),
        'city_id': getattr(user, 'city_id', None),
        'master_secret': secret_value,
    }
    return payload


def encrypt_gpc_payload(payload: dict, master_secret: bytes) -> bytes:
    """
    Encrypt a JSON payload with AES-256-CBC and Android-compatible salt/IV framing.
    The payload format is: salt(16 bytes) + iv(16 bytes) + ciphertext.
    """
    json_str = json.dumps(payload, default=str)
    plaintext = json_str.encode('utf-8')
    master_bytes = master_secret if isinstance(master_secret, bytes) else master_secret.encode('utf-8')
    salt = os.urandom(16)
    iv = os.urandom(16)
    key = derive_key_from_password(master_bytes, salt, 32)
    ciphertext, _ = aes_encrypt(plaintext, key, iv)
    return salt + iv + ciphertext


def decrypt_gpc_payload(encrypted_data: bytes, master_secret: bytes) -> dict:
    """
    Decrypt a GPC payload and support both the Android format (salt+iv+ciphertext)
    and the legacy format (iv+ciphertext with fixed salt).
    """
    if isinstance(encrypted_data, str):
        encrypted_data = encrypted_data.encode('utf-8')

    try:
        decoded_data = base64.b64decode(encrypted_data, validate=False)
        if decoded_data and len(decoded_data) >= 32 and decoded_data != encrypted_data:
            encrypted_data = decoded_data
    except Exception:
        pass

    master_bytes = master_secret if isinstance(master_secret, bytes) else master_secret.encode('utf-8')

    for salt, iv, ciphertext in [
        (encrypted_data[:16], encrypted_data[16:32], encrypted_data[32:]) if len(encrypted_data) >= 32 else (None, None, None),
        (b'gpc_salt_2024', encrypted_data[:16], encrypted_data[16:]) if len(encrypted_data) >= 16 else (None, None, None),
    ]:
        if salt is None or iv is None or ciphertext is None or not ciphertext:
            continue
        try:
            key = derive_key_from_password(master_bytes, salt, 32)
            plaintext = aes_decrypt(ciphertext, key, iv)
            return json.loads(plaintext.decode('utf-8'))
        except Exception:
            continue

    preview = encrypted_data[:32].hex()
    current_app.logger.error(f"Decryption failed: encrypted data preview (hex): {preview}")
    raise ValueError('Decryption failed: invalid GPC payload or mismatched MASTER_SECRET')

def generate_cipher_token() -> str:
    """Generate a cryptographically secure 64-character hex token (32 bytes)."""
    return secrets.token_hex(32)

def derive_session_id() -> str:
    """Generate a unique session identifier (UUID)."""
    return str(uuid.uuid4())

def hash_api_key(raw_key: str) -> str:
    """Return SHA-256 hex digest of the raw API key."""
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

def hash_file_content(file_content: bytes) -> str:
    """Return SHA-256 hex digest of file content for integrity checks."""
    return hashlib.sha256(file_content).hexdigest()

# ==================================================================
# CATALOG PACKAGING
# ==================================================================

def pack_catalog(user_id: int, show_stock: bool = True) -> dict:
    """
    Build a product catalog dictionary for a given user.
    If show_stock is True, include exact stock quantities; otherwise just boolean 'in_stock'.
    """
    from models import Product, Inventory, User, db
    user = User.query.get(user_id)
    if not user:
        return {'products': [], 'error': 'User not found'}

    query = Product.query.filter_by(is_active=True)
    if user.city_id:
        query = query.filter_by(city_id=user.city_id)
    products = query.all()

    result = []
    for p in products:
        total_qty = sum(inv.current_qty for inv in p.inventory_items)
        item = {
            'id': p.id,
            'name': p.name,
            'sku': p.sku,
            'barcode': p.barcode,
            'unit_price': float(p.unit_price),
            'tax_rate': float(p.tax_rate),
            'category': p.category,
            'image_url': p.image_url,
        }
        if show_stock:
            item['stock'] = total_qty
        else:
            item['in_stock'] = total_qty > 0
        result.append(item)
    return {'products': result}

# ==================================================================
# MEDIA MANAGEMENT UTILITIES
# ==================================================================

def build_delete_media_command(user_id: int, media_ids: List[int]) -> dict:
    """Assemble a device command payload to delete specific media files from the device."""
    media_list = Media.query.filter(Media.id.in_(media_ids), Media.user_id == user_id).all()
    if len(media_list) != len(media_ids):
        raise ValueError('Some media IDs do not belong to this user or do not exist.')
    payload = {
        'action': 'DELETE_MEDIA',
        'media_uuids': [m.uuid for m in media_list],
        'file_names': [m.file_name for m in media_list]
    }
    return payload

def create_media_delete_command(user_id: int, media_ids: List[int]) -> DeviceCommand:
    """Create a DeviceCommand record for deleting media."""
    payload = build_delete_media_command(user_id, media_ids)
    cmd = DeviceCommand(
        user_id=user_id,
        command_type='DELETE_MEDIA',
        payload=payload,
        status='PENDING'
    )
    return cmd

# ==================================================================
# GPC FILE GENERATION & PARSING
# ==================================================================

def generate_gpc_file(user_id: int, expiry_days: int, show_stock: bool = True,
                      max_token_cap: int = 15) -> Tuple[bytes, str]:
    """
    Generate a complete .gpc login file for the given user.
    Returns (encrypted_bytes, filename) where filename = username.gpc.
    """
    from models import User, ApiKey, TokenPool, db

    user = User.query.get(user_id)
    if not user:
        raise ValueError('User not found')

    raw_key = secrets.token_hex(32)
    device_uuid = secrets.token_hex(16)
    api_key_hash = hash_api_key(raw_key)

    existing_key = ApiKey.query.filter_by(user_id=user_id, status='ACTIVE').first()
    if existing_key:
        existing_key.device_uuid = device_uuid
        existing_key.api_key_hash = api_key_hash
        existing_key.status = 'ACTIVE'
        existing_key.last_used_at = datetime.utcnow()
    else:
        existing_key = ApiKey(
            device_uuid=device_uuid,
            api_key_hash=api_key_hash,
            user_id=user_id,
            status='ACTIVE'
        )
        db.session.add(existing_key)

    session_id = derive_session_id()
    expiry_date = datetime.utcnow() + timedelta(days=expiry_days)

    token_count = random.randint(1, max_token_cap)
    tokens = []
    for _ in range(token_count):
        token = generate_cipher_token()
        token_record = TokenPool(
            user_id=user_id,
            session_id=session_id,
            cipher_token=token,
            token_status='UNUSED',
            expiry_timestamp=expiry_date
        )
        db.session.add(token_record)
        tokens.append(token)

    db.session.commit()

    catalog = pack_catalog(user_id, show_stock)
    base_url = (
        current_app.config.get('BASE_URL')
        or current_app.config.get('SERVER_URL')
        or (request.host_url.rstrip('/') + '/' if has_request_context() else 'http://localhost:5000/')
    )
    payload = build_gpc_payload(
        user=user,
        api_key=raw_key,
        session_id=session_id,
        device_uuid=existing_key.device_uuid,
        expiry_date=expiry_date,
        catalog=catalog,
        tokens=tokens,
        show_stock=show_stock,
        base_url=base_url,
        master_secret=get_master_secret().decode('utf-8'),
    )

    encrypted = encrypt_gpc_payload(payload, get_master_secret())

    filename = f"{user.username}.gpc"
    return encrypted, filename

def parse_gpc_file(file_content: bytes) -> dict:
    """Decrypt and parse a .gpc file. Returns the decoded payload dictionary."""
    master_secret = get_master_secret()
    if not master_secret:
        raise ValueError("MASTER_SECRET is not set in environment or config.")
    try:
        return decrypt_gpc_payload(file_content, master_secret)
    except Exception as e:
        # Re-raise with a clear message
        raise ValueError(f"Failed to decrypt GPC file: {str(e)}") from e

# ==================================================================
# GPC IMPORT – returns ONLY a summary, not the full payload
# ==================================================================
def import_gpc_export(file_content: bytes) -> dict:
    """
    Process an exported .gpc file (from mobile).
    Returns ONLY a summary, not the full payload (no API keys, tokens, product details).
    """
    payload = parse_gpc_file(file_content)

    # For now, just return a summary (no sensitive data)
    summary = {
        'user_id': payload.get('user_id'),
        'username': payload.get('username'),
        'session_id': payload.get('session_id'),
        'products_in_catalog': len(payload.get('catalog', {}).get('products', [])),
        'tokens_imported': len(payload.get('tokens', [])),
        'expiry_date': payload.get('expiry_date'),
        'show_stock_quantity': payload.get('catalog_permissions', {}).get('show_stock_quantity', False)
    }
    return summary

# ==================================================================
# TOKEN AUTO-REFILL LOGIC
# ==================================================================

def auto_refill_tokens(user_id: int, current_unused: int, max_cap: int, threshold: int) -> List[str]:
    """
    If current_unused <= threshold, generate new tokens (random number up to max_cap - current_unused)
    and return the list of new tokens (as strings). Also inserts them into TokenPool.
    Returns empty list if no refill needed.
    """
    from models import TokenPool, db
    if current_unused > threshold:
        return []

    max_add = max_cap - current_unused
    if max_add <= 0:
        return []
    add_count = random.randint(1, max_add)
    new_tokens = []
    session_id = derive_session_id()
    expiry_date = datetime.utcnow() + timedelta(days=30)

    for _ in range(add_count):
        token = generate_cipher_token()
        tp = TokenPool(
            user_id=user_id,
            session_id=session_id,
            cipher_token=token,
            token_status='UNUSED',
            expiry_timestamp=expiry_date
        )
        db.session.add(tp)
        new_tokens.append(token)

    db.session.commit()
    return new_tokens

# ==================================================================
# COMMAND QUEUE HELPERS
# ==================================================================

def enqueue_delete_media_command(user_id: int, media_ids: List[int]) -> dict:
    """Create and commit a DeviceCommand to delete media from the device."""
    from models import DeviceCommand, db
    cmd = create_media_delete_command(user_id, media_ids)
    db.session.add(cmd)
    db.session.commit()
    return {
        'command_id': cmd.id,
        'command_uuid': cmd.uuid,
        'command_type': cmd.command_type,
        'payload': cmd.payload,
        'status': cmd.status
    }

def get_pending_commands(user_id: int) -> List[dict]:
    """Retrieve all PENDING commands for a user."""
    from models import DeviceCommand
    commands = DeviceCommand.query.filter_by(user_id=user_id, status='PENDING').all()
    result = []
    for cmd in commands:
        result.append({
            'id': cmd.id,
            'uuid': cmd.uuid,
            'command_type': cmd.command_type,
            'payload': cmd.payload,
            'created_at': cmd.created_at.isoformat()
        })
    return result

def mark_command_sent(command_id: int) -> None:
    from models import DeviceCommand, db
    cmd = DeviceCommand.query.get(command_id)
    if cmd:
        cmd.status = 'SENT'
        cmd.sent_at = datetime.utcnow()
        db.session.commit()

def mark_command_acknowledged(command_id: int) -> None:
    from models import DeviceCommand, db
    cmd = DeviceCommand.query.get(command_id)
    if cmd:
        cmd.status = 'ACKNOWLEDGED'
        cmd.acknowledged_at = datetime.utcnow()
        db.session.commit()

# ==================================================================
# MISC HELPER FOR FILE DOWNLOAD
# ==================================================================

def serve_gpc_file(encrypted_bytes: bytes, filename: str):
    """Flask helper to send a .gpc file as attachment."""
    from flask import send_file
    import io
    return send_file(
        io.BytesIO(encrypted_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype='application/octet-stream'
    )
"""
Cria a credencial Telegram diretamente no banco SQLite do n8n,
replicando a criptografia CryptoJS usada internamente pelo n8n.
"""
import hashlib, base64, os, json, sqlite3, uuid
from datetime import datetime

DB_PATH = r"C:\Users\robep\.n8n\database.sqlite"
ENCRYPTION_KEY = "jS/h8P16uGm4JtgXNwVqBrAlyAvZO8DA"
USER_ID = "c667aa2c-6e3b-4534-99a2-4a5650578fdd"
PROJECT_ID = "CfUkV3EULpNhhDLi"
WORKFLOW_ID = "wP740vEMvW5QsJwQ"

TELEGRAM_TOKEN = "8865256559:AAFLB_9mlNyJTTkaE2LitOUL8aPp1YQLTio"

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    PYCRYPTO_OK = True
except ImportError:
    PYCRYPTO_OK = False
    print("PyCryptodome nao disponivel, tentando alternativa...")


def evp_bytes_to_key(password: bytes, salt: bytes, key_len: int, iv_len: int):
    """OpenSSL EVP_BytesToKey — mesma derivacao usada pelo CryptoJS."""
    d, d_i = b"", b""
    while len(d) < key_len + iv_len:
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:key_len], d[key_len:key_len + iv_len]


def encrypt_cryptojs(data: str, key: str) -> str:
    """Replica CryptoJS.AES.encrypt(data, key) — formato OpenSSL/Salted__."""
    salt = os.urandom(8)
    aes_key, iv = evp_bytes_to_key(key.encode(), salt, 32, 16)

    if PYCRYPTO_OK:
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(pad(data.encode(), 16))
    else:
        # Fallback com cryptography package
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding as sym_padding
        padder = sym_padding.PKCS7(128).padder()
        padded = padder.update(data.encode()) + padder.finalize()
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()

    result = b"Salted__" + salt + encrypted
    return base64.b64encode(result).decode()


def main():
    credential_data = json.dumps({"accessToken": TELEGRAM_TOKEN})
    encrypted_data = encrypt_cryptojs(credential_data, ENCRYPTION_KEY)

    cred_id = str(uuid.uuid4()).replace("-", "")[:16]  # n8n usa IDs curtos
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.000")

    nodes_access = json.dumps([{"nodeType": "n8n-nodes-base.telegram"},
                                {"nodeType": "n8n-nodes-base.telegramTrigger"}])

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # Verifica se ja existe
        existing = conn.execute(
            "SELECT id FROM credentials_entity WHERE name = ?",
            ("News Radar Telegram Bot",)
        ).fetchone()

        if existing:
            cred_id = existing["id"]
            conn.execute(
                "UPDATE credentials_entity SET data = ?, updatedAt = ? WHERE id = ?",
                (encrypted_data, now, cred_id)
            )
            print(f"Credencial atualizada: {cred_id}")
        else:
            conn.execute(
                """INSERT INTO credentials_entity
                   (id, name, type, data, createdAt, updatedAt)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cred_id, "News Radar Telegram Bot", "telegramApi",
                 encrypted_data, now, now)
            )
            print(f"Credencial criada: {cred_id}")

        # Vincula ao projeto pessoal do usuario
        conn.execute(
            """INSERT OR IGNORE INTO shared_credentials
               (credentialsId, projectId, role, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?)""",
            (cred_id, PROJECT_ID, "credential:owner", now, now)
        )

        conn.commit()
        print(f"\nCredencial '{cred_id}' criada com sucesso!")
        print("Agora vincule-a ao workflow no n8n UI ou via API.")
        return cred_id

    finally:
        conn.close()


if __name__ == "__main__":
    main()

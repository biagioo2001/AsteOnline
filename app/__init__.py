from flask import Flask
from flask_pymongo import PyMongo
import os
import json
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
import base64
import subprocess
from celery import Celery
from celery.schedules import crontab
from app.blockchain import get_auction_details_from_contract
import logging
from app.shared import shared_state

# Configurazione del logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# L'istanza di MongoDB
mongo = PyMongo()

def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=app.config['result_backend'],
        broker=app.config['broker_url']
    )
    celery.conf.update(app.config)
    return celery


def create_app():
    app = Flask(__name__)
    app.secret_key = os.urandom(24)

    app.config["MONGO_URI"] = "mongodb://localhost:27017/AsteOnline"
    app.config['broker_url'] = 'pyamqp://guest:guest@localhost//'
    app.config['result_backend'] = 'rpc://'

    mongo.init_app(app)

    from .routes import main_bp
    app.register_blueprint(main_bp)

    # Inizializza Celery
    celery = make_celery(app)

    # Carica tutte le aste attive all'avvio del server
    with app.app_context():
        load_active_auctions()

    # Pianificazione del task per chiudere le aste
    celery.conf.beat_schedule = {
        'check-auctions-every-minute': {
            'task': 'run.check_and_close_auctions',
            'schedule': crontab(minute='*/1'),  # Ogni minuto
            'args': (),
        },
    }

    shared_state.add_list_auctions(load_active_auctions())
    return app, celery


def load_active_auctions():
    """Carica tutte le aste attive dal database e le inserisce nella lista active_auctions."""
    global active_auctions
    active_auctions = list(mongo.db.Auctions.find({"is_active": True}))

    for auction in active_auctions:
        auction_id = auction['auction_code']

        try:
            details = get_auction_details_from_contract(auction_id)
            if details:  # Aggiunta verifica per controllare se details è valido
                auction.update({
                    'end_time': details.get('endTime', 'N/A'),
                })
            else:
                auction.update({
                    'end_time': 'N/A',
                })
        except Exception as e:
            logger.error(f"Errore nel recupero dei dettagli dell'asta dalla blockchain: {e}")

    print(f"Aste attive caricate: {len(active_auctions)}")
    return active_auctions


def protect_file_windows(file_path):
    # Disattiva l'ereditarietà dei permessi
    subprocess.run(['icacls', file_path, '/inheritance:r'])

    # Concede pieno controllo all'utente attuale
    subprocess.run(['icacls', file_path, '/grant', f'{os.getlogin()}:F'])

    # Rimuove i permessi di accesso per tutti gli altri
    subprocess.run(['icacls', file_path, '/remove', 'Everyone'])


#   Estrazione account Ganache

def get_next_account():
    file_path = r'C:\Users\biagi\PycharmProjects\Asta\accounts.json'

    # Leggi il file JSON
    with open(file_path, 'r') as f:
        accounts = json.load(f)

    if not accounts:
        raise Exception("No more blockchain accounts available.")

    # Prendi il primo account
    account = accounts.pop(0)

    # Sovrascrivi il file con i restanti account
    with open(file_path, 'w') as f:
        json.dump(accounts, f, indent=4)

    return account


# Funzione per generare una chiave di crittografia dalla password
def generate_key_from_password(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


# Funzione per crittografare la chiave privata e salvarla in un file
def encrypt_private_key(private_key: str, password: str, file_path: str):
    # Genera un sale casuale per la crittografia
    salt = os.urandom(16)

    # Genera la chiave usando la password dell'utente
    key = generate_key_from_password(password, salt)

    # Crea un oggetto Fernet per la crittografia
    fernet = Fernet(key)

    # Crittografa la chiave privata
    encrypted_private_key = fernet.encrypt(private_key.encode())

    # Salva la chiave crittografata e il sale nel file
    with open(file_path, 'wb') as f:
        f.write(salt + b'\n' + encrypted_private_key)

    # Proteggi il file appena creato
    protect_file_windows(file_path)


# Funzione per decrittografare la chiave privata dal file
def decrypt_private_key(password: str, user: str) -> str:

    project_root = os.path.dirname(os.path.abspath(__file__))
    private_key_dir = os.path.join(project_root, 'private_keys')

    if not os.path.exists(private_key_dir):
        os.makedirs(private_key_dir)

    file_path = os.path.join(private_key_dir, f'{user}_private_key.enc')

    with open(file_path, 'rb') as f:
        salt, encrypted_private_key = f.read().split(b'\n')

    key = generate_key_from_password(password, salt)
    fernet = Fernet(key)

    # Decrittografa e restituisce la chiave privata
    return fernet.decrypt(encrypted_private_key).decode()

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response
from werkzeug.security import generate_password_hash, check_password_hash
from . import mongo  # Importa l'istanza di MongoDB
from app import get_next_account, encrypt_private_key, decrypt_private_key
import os
from datetime import datetime  # Importa datetime per gestire le date correttamente
from gridfs import GridFS
import uuid
from app.blockchain import create_auction, get_auction_details_from_contract, get_credit_account, place_bid_on_blockchain, check_and_get_winner
from web3 import Web3
import logging
from bson import ObjectId

# Configura il logger
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

fs = GridFS(mongo.db)

# Definisci una blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Verifica delle credenziali dalla collezione "Clienti"
        user = mongo.db.Clienti.find_one({'username': username})
        if user and check_password_hash(user['password'], password):
            # Memorizza l'utente nella sessione
            session['username'] = username
            session['password'] = password
            session['blockchain_address'] = user['blockchain_address']

            return redirect(url_for('main.home'))
        else:
            flash('Nome utente o password non validi', 'error')
            return render_template('index.html')


@main_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Controlla se l'username esiste già
        user_exists = mongo.db.Clienti.find_one({'username': username})

        if user_exists:
            # Se l'utente esiste già, mostra un messaggio di errore
            flash('Username già esistente. Per favore scegli un altro.', 'error')
            return redirect(url_for('main.register'))

        # Se l'utente non esiste, procedi con l'hashing della password
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Ottieni il prossimo account blockchain disponibile
        try:
            account = get_next_account()
        except Exception as e:
            flash(str(e), 'error')
            return redirect(url_for('main.register'))

        # Crittografa la chiave privata e salvala in un file protetto
        project_root = os.path.dirname(os.path.abspath(__file__))
        private_key_dir = os.path.join(project_root, 'private_keys')

        if not os.path.exists(private_key_dir):
            os.makedirs(private_key_dir)

        private_key_file = os.path.join(private_key_dir, f'{username}_private_key.enc')

        encrypt_private_key(account['private_key'], password, private_key_file)

        # Salva l'utente e l'indirizzo blockchain nel database
        mongo.db.Clienti.insert_one({
            'username': username,
            'password': hashed_password,
            'blockchain_address': account['address']
        })

        flash('Registrazione avvenuta con successo. Per favore effettua il login.', 'success')
        return redirect(url_for('main.index'))

    return render_template('register.html')



@main_bp.route('/home')
def home():
    auctions = mongo.db.Auctions.find({"is_active": True})
    auction_details = []
    session['aggiornamenti'] = None

    user_credit = round(Web3.from_wei(get_credit_account(session['blockchain_address']), 'ether'), 2)

    for auction in auctions:
        auction_id = auction['auction_code']
        try:
            details = get_auction_details_from_contract(auction_id)
            if details:
                highest_bid_in_eur = Web3.from_wei(details['highestBid'], 'ether')
                start_price_in_eur = Web3.from_wei(details['startPrice'], 'ether')

                auction.update({
                    'seller': details['seller'],
                    'highest_bid': highest_bid_in_eur,
                    'highest_bidder': details['highestBidder'],
                    'end_time': details['endTime'],
                    'is_active': details['isActive'],
                    'startPrice': start_price_in_eur
                })
            else:
                auction.update({
                    'highest_bid': 'N/A',
                    'highest_bidder': 'N/A',
                    'end_time': 'N/A',
                    'is_active': False
                })
        except Exception as e:
            flash(f"Errore nel recupero dei dettagli dell'asta dalla blockchain: {e}", 'error')
            logger.error(f"Errore nel recupero dei dettagli dell'asta dalla blockchain: {e}")

        # Converti l'ObjectId in stringa
        auction['_id'] = str(auction['_id'])

        if isinstance(auction.get('end_time'), int):
            auction['end_time'] = datetime.utcfromtimestamp(auction['end_time']).isoformat() + 'Z'
        else:
            auction['end_time'] = auction.get('end_time', 'N/A')

        user = mongo.db.Clienti.find_one({'blockchain_address': auction['seller']})
        auction['seller'] = user.get('username')
        auction_details.append(auction)

    # Salva i dettagli delle aste nella sessione
    session['auction_details'] = auction_details

    return render_template('home.html', auctions=auction_details, user_credit=user_credit, user_name=session['username'])


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@main_bp.route('/create_auction', methods=['GET', 'POST'], endpoint='create_auction')
def create_auction_route():
    from run import memory_update, convert_toString
    from app.shared import shared_state

    if request.method == 'POST':
        if 'username' not in session:
            flash('Devi eseguire il login prima.', 'error')
            return redirect(url_for('main.login'))

        username = session['username']
        password = session['password']
        blockchain_address = session['blockchain_address']

        try:
            private_key = decrypt_private_key(password, username)
        except Exception as e:
            flash('Errore nella decifrazione della chiave privata: ' + str(e), 'error')
            logger.error(f"Errore nella decifrazione della chiave privata: {e}")
            return redirect(url_for('main.create_auction_route'))
        title = request.form['title']
        description = request.form['description']
        starting_price = float(request.form['starting_price'])
        end_time = request.form['end_time']

        auction_code = str(uuid.uuid4())
        image_file_ids = []
        files = [file for key, file in request.files.items() if key.startswith('images[')]
        print(request.files)
        isActive = True

        if len(files) > 5:
            print('Puoi caricare solo fino a 5 foto.', 'error')
            return redirect(request.url)

        for file in files:
            if file and allowed_file(file.filename):
                file_id = fs.put(file, filename=file.filename, content_type=file.content_type)
                image_file_ids.append(str(file_id))
            else:
                flash(f"Tipo di file non valido: {file.filename}", 'error')
                return redirect(request.url)

        try:
            auction_duration = int((datetime.strptime(end_time, "%Y-%m-%dT%H:%M") - datetime.now()).total_seconds())

            create_auction(private_key, auction_code, Web3.to_wei(starting_price, 'ether'), auction_duration, blockchain_address)
        except Exception as e:
            flash(f"Errore nella creazione dell'asta su blockchain: {e}", 'error')
            logger.error(f"Errore nella creazione dell'asta su blockchain: {e}")
            return redirect(request.url)

        auction_data = {
            'title': title,
            'description': description,
            'user_id': username,
            'auction_code': auction_code,
            'images': image_file_ids,
            'created_at': datetime.now(),
            'is_active': isActive
        }

        mongo.db.Auctions.insert_one(auction_data)
        flash('Asta creata con successo e aggiunta alla blockchain!', 'success')

        details = get_auction_details_from_contract(auction_data['auction_code'])

        if details:
            highest_bid_in_eur = Web3.from_wei(details['highestBid'], 'ether')
            start_price_in_eur = Web3.from_wei(details['startPrice'], 'ether')

            auction_data.update({
                'seller': details['seller'],
                'highest_bid': highest_bid_in_eur,
                'highest_bidder': details['highestBidder'],
                'end_time': details['endTime'],
                'is_active': details['isActive'],
                'startPrice': start_price_in_eur
            })
        else:
            auction_data.update({
                'highest_bid': 'N/A',
                'highest_bidder': 'N/A',
                'end_time': 'N/A',
                'is_active': False
            })

        # Aggiungi l'asta appena creata nella lista delle aste attive
        shared_state.add_auction(auction_data)
        auction_data = convert_toString(auction_data)
        memory_update.delay(auction_data)
        print(len(shared_state.get_active_auctions()))

        return redirect(url_for('main.home'))

    return render_template('create_auction.html')


@main_bp.route('/auction/<int:auction_index>')
def auction_details(auction_index):
    # Ottieni la lista delle aste dalla sessione
    auctions = session.get('auction_details')  # Assumiamo che tu abbia salvato la lista nella sessione
    # Verifica che auctions sia una lista e che l'indice sia valido
    if auctions and isinstance(auctions, list) and 0 <= auction_index < len(auctions):
        if(session.get('aggiornamenti') is None):
            auction = auctions[auction_index]
        else:
            auction = session['aggiornamenti']
        # Passa auction_index alla template insieme ad auction
        user = mongo.db.Clienti.find_one({'blockchain_address': auction['highest_bidder']})
    if (user is not None):
        auction['highest_bidder'] = user.get('username')
    else:
        auction['highest_bidder'] = None

    user_credit = round(Web3.from_wei(get_credit_account(session['blockchain_address']), 'ether'), 2)

    return render_template('auction_details.html', auction=auction, auction_index=auction_index, user_credit=user_credit, user_name=session['username'])
    # Se non si trova l'asta, mostra un messaggio di errore
    flash('Asta non trovata.', 'error')
    return redirect(url_for('main.home'))



@main_bp.route('/logout')
def logout():
    # Rimuovi tutti i dati dalla sessione
    session.clear()
    flash('Logout effettuato con successo!', 'success')
    return redirect(url_for('main.index'))

@main_bp.route('/image/<file_id>')
def get_image(file_id):
    try:
        file = fs.get(ObjectId(file_id))
        return Response(file.read(), mimetype=file.content_type)
    except Exception as e:
        return str(e), 404


@main_bp.route('/place_bid/<int:auction_index>', methods=['POST'])
def place_bid(auction_index):
    bid_amount = request.form.get('bid_amount', type=float)

    private_key = decrypt_private_key(session['password'], session['username'])

    if not private_key:
        flash('Non sei autenticato.', 'error')
        return redirect(url_for('main.login'))
    print(session['auction_details'][auction_index])
    # Ottieni la lista delle aste dalla sessione
    auctions = session.get('auction_details')
    if auctions and 0 <= auction_index < len(auctions):
        auction = auctions[auction_index]
        auction_id = auction.get('auction_code')

        # Esegui l'offerta
        try:
            place_bid_on_blockchain(private_key, session['blockchain_address'], auction_id, Web3.to_wei(bid_amount, 'ether'))
            print('Offerta piazzata con successo!')

            # Ottieni i dettagli aggiornati dell'asta
            updated_details = get_auction_details_from_contract(auction_id)
            if updated_details:
                auction.update({
                    'highest_bid': Web3.from_wei(updated_details['highestBid'], 'ether'),
                    'highest_bidder': updated_details['highestBidder'],
                    'is_active': updated_details['isActive'],
                })

                # Aggiorna la sessione con i dettagli aggiornati
                session['aggiornamenti'] = auction

        except Exception as e:
            flash(f'Errore durante l\'offerta: {str(e)}', 'error')

    else:
        flash('Asta non trovata.', 'error')

    return redirect(url_for('main.auction_details', auction_index=auction_index))


@main_bp.route('/won_auctions')
def won_auctions():
    if 'username' not in session:
        flash('Devi eseguire il login per vedere le aste vinte.', 'error')
        return redirect(url_for('main.login'))

    username = session['username']
    blockchain_address = session['blockchain_address']

    # Recupera tutte le aste concluse
    ended_auctions = mongo.db.Auctions.find({"is_active": False})

    won_auction_details = []

    for auction in ended_auctions:
        auction_id = auction['auction_code']

        # Verifica il vincitore utilizzando la funzione della blockchain
        try:
            winner = check_and_get_winner(auction_id)
        except Exception as e:
            logger.error(f"Errore nel controllo del vincitore per l'asta {auction_id}: {e}")
            flash(f"Errore nel recupero delle aste vinte: {e}", 'error')
            continue

        if winner is not None:
            # Se l'indirizzo blockchain dell'utente corrente è il vincitore
            if winner['highestBidder'] == blockchain_address:
                venditore = mongo.db.Clienti.find_one({"blockchain_address": winner['seller']})
                auction.update({
                    'seller': venditore['username'],
                    'highest_bid': Web3.from_wei(winner['highestBid'], 'ether'),
                    'highest_bidder': winner['highestBidder'],
                    'final_price': Web3.from_wei(winner['highestBid'], 'ether'),
                    'is_active': winner['isActive']
                })

                # Converti l'end_time in un formato più leggibile (senza T e Z)
                try:
                    end_time = datetime.utcfromtimestamp(winner['endTime'])
                    auction['end_time'] = end_time.strftime('%d/%m/%Y %H:%M:%S')
                except (ValueError, KeyError):
                    auction['end_time'] = 'N/A'

                # Converti l'ObjectId in stringa
                auction['_id'] = str(auction['_id'])

                # Se l'asta ha immagini, converti gli ID in stringhe
                auction['images'] = [str(image_id) for image_id in auction.get('images', [])]

                # Aggiungi l'asta alla lista delle aste vinte
                won_auction_details.append(auction)

    user_credit = round(Web3.from_wei(get_credit_account(session['blockchain_address']), 'ether'), 2)

    # Mostra la pagina con le aste vinte
    return render_template('won_auctions.html', won_auctions=won_auction_details, user_credit=user_credit, user_name=username)

@main_bp.route('/my_auctions')
def my_auctions():
    if 'username' not in session:
        flash('Devi eseguire il login per vedere le aste create.', 'error')
        return redirect(url_for('main.login'))

    username = session['username']
    blockchain_address = session['blockchain_address']

    # Recupera tutte le aste create dall'utente loggato
    user_created_auctions = mongo.db.Auctions.find({"user_id": username})

    active_auctions = []
    sold_auctions = []
    unsold_auctions = []

    for auction in user_created_auctions:
        auction_id = auction['auction_code']

        # Recupera i dettagli dell'asta dalla blockchain
        try:
            auction_details = get_auction_details_from_contract(auction_id)
        except Exception as e:
            logger.error(f"Errore nel recupero dei dettagli dell'asta {auction_id}: {e}")
            flash(f"Errore nel recupero delle aste create: {e}", 'error')
            continue

        if auction_details:
            # Converti i dettagli dell'asta dalla blockchain
            highest_bid_in_eur = Web3.from_wei(auction_details['highestBid'], 'ether')
            start_price_in_eur = Web3.from_wei(auction_details['startPrice'], 'ether')

            # Recupera l'acquirente con l'offerta più alta
            cliente = mongo.db.Clienti.find_one({"blockchain_address": auction_details['highestBidder']})
            highest_bidder_username = cliente['username'] if cliente else None

            auction.update({
                'seller': auction_details['seller'],
                'highest_bid': highest_bid_in_eur,
                'highest_bidder': highest_bidder_username,
                'end_time': auction_details['endTime'],
                'is_active': auction_details['isActive'],
                'startPrice': start_price_in_eur
            })

            user = mongo.db.Clienti.find_one({'blockchain_address': auction['seller']})

            if(user != None):
                auction['seller'] = user.get('username')

            # Converti l'end_time in un formato leggibile
            try:
                end_time = datetime.utcfromtimestamp(auction['end_time']).isoformat() + 'Z'
                auction['end_time'] = end_time
            except (ValueError, KeyError):
                auction['end_time'] = 'N/A'

            # Suddividi le aste in attive, vendute e invendute
            if auction_details['isActive']:
                # Aste attive
                active_auctions.append(auction)
            elif auction_details['highestBid'] > 0:
                # Aste vendute (scadute con offerte)
                sold_auctions.append(auction)
            else:
                # Aste invendute (scadute senza offerte)
                unsold_auctions.append(auction)

        # Converti l'ObjectId in stringa per evitare problemi di serializzazione
        auction['_id'] = str(auction['_id'])

        # Se l'asta ha immagini, converti gli ID delle immagini in stringhe
        auction['images'] = [str(image_id) for image_id in auction.get('images', [])]

    # Recupera il credito utente dalla blockchain
    user_credit = round(Web3.from_wei(get_credit_account(blockchain_address), 'ether'), 2)

    session['auction_details'] = active_auctions
    # Passa i dati al template: aste attive, vendute, invendute, credito utente e nome utente
    return render_template(
        'my_auctions.html',
        active_auctions=active_auctions,
        sold_auctions=sold_auctions,
        unsold_auctions=unsold_auctions,
        user_credit=user_credit,
        user_name=username
    )


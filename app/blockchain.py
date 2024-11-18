import json
import os
from web3 import Web3
from solcx import compile_standard, install_solc, set_solc_version, get_solc_version
from solcx.exceptions import SolcNotInstalled

# Configura la connessione a Ganache come variabile d'ambiente
GANACHE_URL = os.getenv("GANACHE_URL", "http://127.0.0.1:7545")
web3 = Web3(Web3.HTTPProvider(GANACHE_URL))

# Verifica se la connessione è riuscita
if not web3.is_connected():
    raise Exception("Connessione a Ganache fallita!")

# File contenente il contratto Solidity
CONTRACT_FILE = r"C:\Users\biagi\PycharmProjects\Asta\app\contract\AuctionContract.sol"
COMPILED_CONTRACT = r"C:\Users\biagi\PycharmProjects\Asta\app\contract\AuctionContract.json"
SOLC_VERSION = '0.8.0'
ADDRESS_CONTRACT = '0xD7C5901F7136FA569707a119ad22e25126c56383'


def compile_smart_contract():
    """
    Compila il contratto Solidity e lo salva in un file JSON se non già esistente.
    """
    if os.path.exists(COMPILED_CONTRACT):
        print("Contratto già compilato. Salto la compilazione.")
        return

    try:
        # Verifica e imposta la versione di solc
        try:
            installed_versions = get_solc_version()
            if SOLC_VERSION not in installed_versions:
                install_solc(SOLC_VERSION)
        except SolcNotInstalled:
            install_solc(SOLC_VERSION)

        set_solc_version(SOLC_VERSION)
    except Exception as e:
        print(f"Errore durante la verifica o l'installazione di solc: {e}")
        return None

    try:
        with open(CONTRACT_FILE, "r") as file:
            auction_contract_source = file.read()
    except FileNotFoundError:
        print(f"Errore: File {CONTRACT_FILE} non trovato!")
        return None

    try:
        compiled_sol = compile_standard({
            "language": "Solidity",
            "sources": {os.path.basename(CONTRACT_FILE): {"content": auction_contract_source}},
            "settings": {
                "outputSelection": {
                    "*": {
                        "*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]
                    }
                }
            }
        })

        # Salva il contratto compilato in un file JSON
        with open(COMPILED_CONTRACT, "w") as file:
            json.dump(compiled_sol, file)
    except Exception as e:
        print(f"Errore durante la compilazione o il salvataggio: {e}")
        return None

    return compiled_sol


def deploy_smart_contract(private_key, address):
    """
    Esegue il deploy del contratto sulla blockchain di Ganache solo se non esiste già.
    """
    if os.path.exists('indirizzo_contratto_salvato.txt'):
        with open('indirizzo_contratto_salvato.txt', 'r') as f:
            return f.read().strip()

    print("Caricamento del contratto compilato...")
    try:
        with open(COMPILED_CONTRACT, "r") as file:
            compiled_sol = json.load(file)
            print("File JSON caricato con successo.")
    except FileNotFoundError:
        print(f"Errore: File {COMPILED_CONTRACT} non trovato!")
        return None
    except json.JSONDecodeError as e:
        print(f"Errore nel caricamento del JSON: {e}")
        return None

    try:
        contract_file_name = os.path.basename(CONTRACT_FILE)
        contract_abi = compiled_sol["contracts"][contract_file_name]["AuctionContract"]["abi"]
        contract_bytecode = compiled_sol["contracts"][contract_file_name]["AuctionContract"]["evm"]["bytecode"][
            "object"]

        print("ABI e Bytecode recuperati con successo.")
    except KeyError as e:
        print(f"Errore: Chiave mancante nel file JSON: {e}")
        return None

    auction_contract = web3.eth.contract(abi=contract_abi, bytecode=contract_bytecode)
    nonce = web3.eth.get_transaction_count(address)

    tx = auction_contract.constructor().build_transaction({
        'from': address,
        'nonce': nonce,
        'gas': 6721975,
        'gasPrice': web3.to_wei('1', 'gwei')
    })
    print(f"Dettagli della transazione: {tx}")

    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    print("Transazione firmata con successo.")

    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"Transazione inviata. Hash: {tx_hash.hex()}")

    tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print("Transazione confermata.")

    return tx_receipt.contractAddress


def load_smart_contract(contract_address):
    """
    Carica il contratto dal suo indirizzo sulla blockchain.
    """
    with open(COMPILED_CONTRACT, "r") as file:
        compiled_sol = json.load(file)

    contract_file_name = os.path.basename(CONTRACT_FILE)
    contract_abi = compiled_sol["contracts"][contract_file_name]["AuctionContract"]["abi"]
    contract = web3.eth.contract(address=contract_address, abi=contract_abi)
    return contract


def create_auction(private_key, auction_id, start_price, duration, account_address):
    """
    Crea una nuova asta e invia la transazione firmata con la chiave privata dell'utente.
    """
    contract = load_smart_contract(ADDRESS_CONTRACT)
    nonce = web3.eth.get_transaction_count(account_address)
    # Stima del gas
    # Costruzione della transazione
    tx = contract.functions.createAuction(
        auction_id,  # ID dell'asta come stringa
        start_price,  # Prezzo di partenza come uint256
        duration  # Durata dell'asta come uint256
    ).build_transaction({
        'from': account_address,
        'nonce': nonce,
        'gas': 666678,
        'gasPrice': web3.to_wei('1', 'gwei')
    })

    # Firma della transazione
    signed_tx = web3.eth.account.sign_transaction(tx, private_key)

    # Invia la transazione
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)

    # Attendi la conferma della transazione
    web3.eth.wait_for_transaction_receipt(tx_hash)

    print(f"Asta creata con successo. Hash transazione: {tx_hash.hex()}")

def place_bid_on_blockchain(private_key, address, auction_id, bid_amount):
    """
    Fai un'offerta per un'asta.
    """
    contract = load_smart_contract(ADDRESS_CONTRACT)
    nonce = web3.eth.get_transaction_count(address)

    gas_estimate = 200000

    tx = contract.functions.bid(auction_id).build_transaction({
        'from': address,
        'nonce': nonce,
        'value': bid_amount,
        'gas': gas_estimate,
        'gasPrice': web3.to_wei('1', 'gwei')
    })

    signed_tx = web3.eth.account.sign_transaction(tx, private_key)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
    web3.eth.wait_for_transaction_receipt(tx_hash)
    print(f"Offerta di {web3.from_wei(bid_amount, 'ether')} ETH piazzata per l'asta {auction_id}")


def close_auction_on_blockchain(auction_id):
    # Logica per interagire con la blockchain e chiudere l'asta
    auction_details = get_auction_details_from_contract(auction_id)

    contract = load_smart_contract(ADDRESS_CONTRACT)

    if auction_details['isActive'] is True:
        # Supponendo che ci sia una funzione `endAuction` nel contratto
        transaction = contract.functions.endAuction(auction_id).transact({'from': auction_details['seller']})
        return transaction
    return None


def get_auction_details_from_contract(auction_id):
    try:
        contract = load_smart_contract(ADDRESS_CONTRACT)
        result = contract.functions.getAuctionDetails(auction_id).call()

        details = {
            'seller': result[0],
            'startPrice': result[1],
            'highestBid': result[2],
            'highestBidder': result[3],
            'endTime': result[4],
            'isActive': result[5]
        }
        return details

    except Exception as e:
        print(f"Errore nel recupero dei dettagli dell'asta: {e}")
        return None


# Esempio di utilizzo delle funzioni
if __name__ == "__main__":
    compile_smart_contract()
    print('Contratto='+deploy_smart_contract('0x2ef0742fb7583d7b361d9ed0ae48c539091bfd7c4a3055079263d0a9fd2c1925', '0x7027F34320dDDF8825741D58B90DCeF73De9c2f3'))

def get_credit_account(account_address):
    return web3.eth.get_balance(account_address)


def check_and_get_winner(auction_id):
    """
    Controlla se l'asta è scaduta e ritorna l'indirizzo del vincitore.
    Se non ci sono offerte, non ritorna alcun vincitore.
    """

    auction_details = get_auction_details_from_contract(auction_id)

    # Verifica se l'asta è attiva
    if auction_details['isActive']:
        print(f"L'asta {auction_id} è ancora attiva. Nessun vincitore determinato.")
        return None

    # Verifica se ci sono offerte
    if auction_details['highestBidder'] == '0x0000000000000000000000000000000000000000':
        print(f"L'asta {auction_id} è scaduta ma non ci sono offerte. Nessun vincitore.")
        return None

    # Se l'asta è scaduta e c'è un offerente, è il vincitore
    print(f"Il vincitore dell'asta {auction_id} è: {auction_details['highestBidder']}")
    return auction_details

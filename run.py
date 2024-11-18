from app import create_app
from app.blockchain import close_auction_on_blockchain
import datetime
from datetime import datetime
import logging
from app import mongo
from app.shared import shared_state
from bson.objectid import ObjectId


app, celery = create_app()


if __name__ == "__main__":
    app.run(debug=True)


# Set up logging
logging.basicConfig(level=logging.INFO)

@celery.task
def check_and_close_auctions():
    logging.info("Checking auctions...")  # Improved logging

    current_time = datetime.now()
    active_auctions = shared_state.get_active_auctions()
    print(len(active_auctions))
    print(active_auctions)

    for auction in active_auctions:
        end_time = auction.get('end_time')

        print(datetime.fromtimestamp(end_time))
        print(current_time)
        # Verify if the auction has expired
        if end_time and current_time > datetime.fromtimestamp(end_time):
            auction_id = auction['auction_code']

            try:
                # Close the auction on the blockchain
                close_auction_on_blockchain(auction_id)

                # Update the auction status in the database
                mongo.db.Auctions.update_one(
                    {"auction_code": auction_id},
                    {"$set": {"is_active": False}}
                )

                # Remove the auction from the active_auctions list
                active_auctions = [a for a in active_auctions if a['auction_code'] != auction_id]
                logging.info(f"Auction {auction_id} closed successfully")

            except Exception as e:
                logging.error(f"Error closing auction {auction_id}: {e}")

@celery.task
def memory_update(auction):
    shared_state.add_auction(convert_to_object(auction))

def convert_toString(data):
    if isinstance(data, dict):
        return {key: convert_toString(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_toString(item) for item in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data

def convert_to_object(data):
    if isinstance(data, dict):
        return {key: convert_to_object(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [convert_to_object(item) for item in data]
    elif isinstance(data, str):
        try:
            return ObjectId(data)  # Prova a convertire la stringa in ObjectId
        except:
            return data  # Se non è una stringa valida per ObjectId, restituisci il valore originale
    else:
        return data


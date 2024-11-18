import threading

class SharedStateSingleton:
    """Classe Singleton per gestire lo stato condiviso in memoria con thread safety."""
    _instance = None
    _lock = threading.Lock()  # Lock per gestire accessi concorrenti

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(SharedStateSingleton, cls).__new__(cls)
                    cls._instance.active_auctions = []
        return cls._instance

    def add_auction(self, auction):
        """Aggiunge un'asta alla lista delle aste attive."""
        with self._lock:
            self.active_auctions.append(auction)

    def remove_auction(self, auction_id):
        """Rimuove un'asta dalla lista delle aste attive in base all'ID."""
        with self._lock:
            self.active_auctions = [a for a in self.active_auctions if a['auction_code'] != auction_id]

    def get_active_auctions(self):
        """Restituisce la lista delle aste attive."""
        with self._lock:
            return self.active_auctions.copy()

    def add_list_auctions(self, auction_list):
        """Aggiunge una lista di aste alla lista delle aste attive."""
        with self._lock:
            self.active_auctions.extend(auction_list)

# Istanza globale del Singleton, che può essere importata ovunque
shared_state = SharedStateSingleton()

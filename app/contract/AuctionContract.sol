//SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract AuctionContract {

    struct Auction {
        string auctionId; // auctionId è una stringa ora
        address payable seller;
        uint256 startPrice;
        uint256 highestBid;
        address payable highestBidder;
        uint256 endTime;
        bool isActive;
        mapping(address => uint256) pendingReturns;
    }

    mapping(string => Auction) public auctions; // Mappatura con stringa come chiave

    event AuctionCreated(string auctionId, address seller, uint256 startPrice, uint256 endTime);
    event NewBid(string auctionId, address bidder, uint256 amount);
    event AuctionEnded(string auctionId, address winner, uint256 amount);

    function createAuction(string calldata _auctionId, uint256 _startPrice, uint256 _duration) external {
        require(_duration > 0, "La durata deve essere maggiore di zero");
        require(bytes(_auctionId).length > 0, "L'ID dell'asta non puo' essere vuoto");  // Assicurarsi che l'ID non sia vuoto
        require(auctions[_auctionId].seller == address(0), "L'ID dell'asta esiste gia'");  // Controllo se l'asta esiste già

        Auction storage newAuction = auctions[_auctionId];
        newAuction.auctionId = _auctionId;  // Imposta l'ID dell'asta come stringa
        newAuction.seller = payable(msg.sender);
        newAuction.startPrice = _startPrice;
        newAuction.highestBid = 0;
        newAuction.highestBidder = payable(address(0));
        newAuction.endTime = block.timestamp + _duration;
        newAuction.isActive = true;

        emit AuctionCreated(_auctionId, msg.sender, _startPrice, newAuction.endTime);
    }

 function bid(string calldata _auctionId) external payable {
    Auction storage auction = auctions[_auctionId];

    require(block.timestamp < auction.endTime, "L'asta e' terminata");
    require(auction.isActive, "L'asta non e' piu' attiva");
    require(msg.value > auction.startPrice, "L'offerta deve essere superiore al prezzo iniziale");
    require(msg.value > auction.highestBid, "L'offerta deve essere superiore all'offerta piu' alta");

    address previousBidder = auction.highestBidder; // Questo è di tipo address
    uint256 previousBid = auction.highestBid;

    auction.highestBidder = payable(msg.sender); // Assicurati che il mittente sia di tipo payable
    auction.highestBid = msg.value;

    if (previousBid > 0) {
        // Invia i fondi al precedente offerente usando transfer
        payable(previousBidder).transfer(previousBid); // Cast a payable
    }

    emit NewBid(_auctionId, msg.sender, msg.value);
}


    function withdraw(string calldata _auctionId) external returns (bool) {
        Auction storage auction = auctions[_auctionId];
        uint256 amount = auction.pendingReturns[msg.sender];

        if (amount > 0) {
            auction.pendingReturns[msg.sender] = 0;

            if (!payable(msg.sender).send(amount)) {
                auction.pendingReturns[msg.sender] = amount;
                return false;
            }
        }
        return true;
    }

    function endAuction(string calldata _auctionId) external {
        Auction storage auction = auctions[_auctionId];

        require(auction.isActive, "L'asta e' gia' terminata");

        auction.isActive = false;

        if (auction.highestBidder != address(0)) {
            auction.seller.transfer(auction.highestBid);
            emit AuctionEnded(_auctionId, auction.highestBidder, auction.highestBid);
        }
    }

    function getAuctionDetails(string calldata _auctionId) external view returns (
        address seller,
        uint256 startPrice,
        uint256 highestBid,
        address highestBidder,
        uint256 endTime,
        bool isActive
    ) {
        Auction storage auction = auctions[_auctionId];
        return (
            auction.seller,
            auction.startPrice,
            auction.highestBid,
            auction.highestBidder,
            auction.endTime,
            auction.isActive
        );
    }
}
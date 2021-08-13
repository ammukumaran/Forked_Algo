import logging
from datetime import datetime
from math import floor

from core.Quotes import Quotes
from instruments.Instruments import Instruments
from models.Direction import Direction
from models.ProductType import ProductType
from strategies.BaseStrategy import BaseStrategy
from trademgmt.Trade import Trade
from trademgmt.TradeManager import TradeManager
from utils.Utils import Utils


# Each strategy has to be derived from BaseStrategy
class ShortStraddleStrangleBNFhedge(BaseStrategy):
    __instance = None

    @staticmethod
    def getInstance():  # singleton class
        if ShortStraddleStrangleBNFhedge.__instance == None:
            ShortStraddleStrangleBNFhedge()
        return ShortStraddleStrangleBNFhedge.__instance

    def __init__(self):
        if ShortStraddleStrangleBNFhedge.__instance != None:
            raise Exception("This class is a singleton!")
        else:
            ShortStraddleStrangleBNFhedge.__instance = self
        # Call Base class constructor
        super().__init__("ShortStraddleStrangleBNFhedge")
        # Initialize all the properties specific to this strategy
        self.productType = ProductType.MIS
        self.symbols = []
        self.slPercentage = 30
        self.targetPercentage = 0
        self.startTimestamp = Utils.getTimeOfToDay(9, 45, 0)  # When to start the strategy. Default is Market start time
        self.stopTimestamp = Utils.getTimeOfToDay(10, 50,
                                                  0)  # This is not square off timestamp. This is the timestamp after which no new trades will be placed under this strategy but existing trades continue to be active.
        self.squareOffTimestamp = Utils.getTimeOfToDay(15, 5, 0)  # Square off time
        self.capital = 300000  # Capital to trade (This is the margin you allocate from your broker account for this strategy)
        self.leverage = 0
        self.maxTradesPerDay = 6  # (2 CE + 2 PE + 2 Hedge) Max number of trades per day under this strategy
        self.isFnO = True  # Does this strategy trade in FnO or not
        self.capitalPerSet = 150000  # Applicable if isFnO is True (1 set means 1CE/1PE or 2CE/2PE etc based on your strategy logic)

        self.strategyTSL = True
        self.strategySL = -13500
        self.strategyTGT = 10000
        self.strategyTGTlock = 6000
        self.strategyTrailPLInc = 400
        self.strategyTrailPLstep = 200
        self.strategyExit = False

    def canTradeToday(self):
        # Even if you remove this function canTradeToday() completely its same as allowing trade every day
        return True

    def process(self):
        now = datetime.now()
        if now < self.startTimestamp:
            logging.error("selva")
            return
        if len(self.trades) >= self.maxTradesPerDay:
            logging.error("selva1")
            return

        # Get current market price of Nifty Future
        futureSymbol = Utils.prepareMonthlyExpiryFuturesSymbol('BANKNIFTY')
        quote = self.getQuote(futureSymbol)
        # quote = self.getQuote('NIFTY BANK') # Taken SPOT Price for ATM
        # quote = Quotes.getQuote("NIFTY BANK",False) # Taken SPOT Price for ATM False for NSE True for NFO
        quote = Quotes.getStrikePrice("NIFTY BANK")
        if quote == None:
            logging.error('%s: Could not get quote for %s', self.getName(), futureSymbol)
            return

        # ATMStrike = Utils.getNearestStrikePrice(quote.lastTradedPrice, 100)
        # logging.info('%s: Nifty CMP = %f, ATMStrike = %d', self.getName(), quote.lastTradedPrice, ATMStrike)

        ATMStrike = Utils.getNearestStrikePrice(quote, 100)
        logging.info('%s: %s = %f, ATMStrike = %d', self.getName(), futureSymbol, quote, ATMStrike)

        # Hedging Code
        initialATMStrike = ATMStrike + 100
        ShortStraddleStrangleBNFhedge.trades = []
        logging.info("Selecting Hedging Trades...")
        # Increment from current ATM strike price to find strike that condition met to CE strike
        while True:
            tempSymbol = Utils.prepareWeeklyOptionsSymbol("BANKNIFTY", initialATMStrike, 'CE')
            optionQuote = Quotes.getOptionHedgingQuote(tempSymbol, True)
            if (ShortStraddleStrangleBNFhedge.isWithinTradingRange(optionQuote.lastTradedPrice)):
                message = "{0} : low is {1} satisfies to trade".format(optionQuote.tradingSymbol,
                                                                       optionQuote.lastTradedPrice)
                logging.info(message)
                break
            initialATMStrike = initialATMStrike + 100
        CEhedgeSymbol = tempSymbol

        # Increment from current ATM strike price to find strike that condition met to PE strike
        initialATMStrike = ATMStrike - 100
        while True:
            tempSymbol = Utils.prepareWeeklyOptionsSymbol("BANKNIFTY", initialATMStrike, 'PE')
            optionQuote = Quotes.getOptionHedgingQuote(tempSymbol, True)
            if (ShortStraddleStrangleBNFhedge.isWithinTradingRange(optionQuote.lastTradedPrice)):
                message = "{0} : low is {1} satisfies to trade".format(optionQuote.tradingSymbol,
                                                                       optionQuote.lastTradedPrice)
                logging.info(message)
                break
            initialATMStrike = initialATMStrike - 100
        PEhedgeSymbol = tempSymbol
        # end Hedging

        ATMCESymbol = Utils.prepareWeeklyOptionsSymbol("BANKNIFTY", ATMStrike, 'CE')
        ATMPESymbol = Utils.prepareWeeklyOptionsSymbol("BANKNIFTY", ATMStrike, 'PE')
        logging.info('%s: ATMCESymbol = %s, ATMPESymbol = %s', self.getName(), ATMCESymbol, ATMPESymbol)

        OTMCESymbol = Utils.prepareWeeklyOptionsSymbol("BANKNIFTY", ATMStrike + 400, 'CE')
        OTMPESymbol = Utils.prepareWeeklyOptionsSymbol("BANKNIFTY", ATMStrike - 400, 'PE')
        logging.info('%s: OTMCESymbol = %s, OTMPESymbol = %s', self.getName(), OTMCESymbol, OTMPESymbol)

        # create trades
        self.generateHedgetrades(CEhedgeSymbol, PEhedgeSymbol)
        self.generateATMtrades(ATMCESymbol, ATMPESymbol)
        self.generateOTMtrades(OTMCESymbol, OTMPESymbol)
        Utils.sendMessageTelegramBot("BNF Straddle Strangle Strategy Entered...")

    def generateATMtrades(self, ATMCESymbol, ATMPESymbol):
        numLots = self.calculateLotsPerTrade()
        quoteATMCESymbol = self.getQuote(ATMCESymbol)
        quoteATMPESymbol = self.getQuote(ATMPESymbol)
        if quoteATMCESymbol == None or quoteATMPESymbol == None:
            logging.error('%s: Could not get quotes for option symbols', self.getName())
            return

        self.generateTrade(ATMCESymbol, numLots, quoteATMCESymbol.lastTradedPrice)
        self.generateTrade(ATMPESymbol, numLots, quoteATMPESymbol.lastTradedPrice)
        logging.info('%s: Trades generated.', self.getName())

    def generateOTMtrades(self, ATMCESymbol, ATMPESymbol):
        numLots = self.calculateLotsPerTrade() * 2  # multiply by 2 for OTM LOTs with restpect to ATM
        quoteATMCESymbol = self.getQuote(ATMCESymbol)
        quoteATMPESymbol = self.getQuote(ATMPESymbol)
        if quoteATMCESymbol == None or quoteATMPESymbol == None:
            logging.error('%s: Could not get quotes for option symbols', self.getName())
            return

        self.generateTrade(ATMCESymbol, numLots, quoteATMCESymbol.lastTradedPrice)
        self.generateTrade(ATMPESymbol, numLots, quoteATMPESymbol.lastTradedPrice)
        logging.info('%s: Trades generated.', self.getName())

    def generateHedgetrades(self, CEhedgeSymbol, PEhedgeSymbol):
        numLots = self.calculateLotsPerTrade() * 3  # for both ATM and OTM at 10pt OTM strike
        quotehedgeCESymbol = self.getQuote(CEhedgeSymbol)
        quotehedgePESymbol = self.getQuote(PEhedgeSymbol)
        if quotehedgeCESymbol == None or quotehedgePESymbol == None:
            logging.error('%s: Could not get quotes for option symbols', self.getName())
            return
        self.generateHedge(CEhedgeSymbol, numLots, quotehedgeCESymbol.lastTradedPrice)
        self.generateHedge(PEhedgeSymbol, numLots, quotehedgePESymbol.lastTradedPrice)
        logging.info('%s: Hedge Trades generated...', self.getName())

    def generateTrade(self, optionSymbol, numLots, lastTradedPrice):
        trade = Trade(optionSymbol)
        trade.strategy = self.getName()
        trade.isOptions = True
        trade.direction = Direction.SHORT  # Always short here as option selling only
        trade.productType = self.productType
        trade.placeMarketOrder = True
        trade.requestedEntry = lastTradedPrice

        trade.strategyTSL = self.strategyTSL
        trade.strategySL = self.strategySL
        trade.strategyTGT = self.strategyTGT
        trade.strategyTGTlock = self.strategyTGTlock
        trade.strategyTrailPLInc = self.strategyTrailPLInc
        trade.strategyTrailPLstep = self.strategyTrailPLstep
        trade.strategyExit = self.strategyExit

        trade.timestamp = Utils.getEpoch(self.startTimestamp)  # setting this to strategy timestamp

        isd = Instruments.getInstrumentDataBySymbol(optionSymbol)  # Get instrument data to know qty per lot
        trade.qty = isd['lot_size'] * numLots

        trade.stopLoss = Utils.roundToNSEPrice(trade.requestedEntry + trade.requestedEntry * self.slPercentage / 100)
        trade.target = 0  # setting to 0 as no target is applicable for this trade

        trade.intradaySquareOffTimestamp = Utils.getEpoch(self.squareOffTimestamp)
        # Hand over the trade to TradeManager
        TradeManager.addNewTrade(trade)

    def generateHedge(self, optionSymbol, numLots, lastTradedPrice):
        trade = Trade(optionSymbol)
        trade.strategy = self.getName()
        trade.isOptions = True
        trade.direction = Direction.LONG  # Always LONG here as option buying only
        trade.productType = self.productType
        trade.placeMarketOrder = True
        trade.requestedEntry = lastTradedPrice

        # no Strategy TSL
        # trade.strategyTSL = self.strategyTSL
        # trade.strategySL = self.strategySL
        # trade.strategyTGT = self.strategyTGT
        # trade.strategyTGTlock = self.strategyTGTlock
        # trade.strategyTrailPLInc = self.strategyTrailPLInc
        # trade.strategyTrailPLstep = self.strategyTrailPLstep
        # trade.strategyExit = self.strategyExit

        trade.timestamp = Utils.getEpoch(self.startTimestamp)  # setting this to strategy timestamp

        isd = Instruments.getInstrumentDataBySymbol(optionSymbol)  # Get instrument data to know qty per lot
        trade.qty = isd['lot_size'] * numLots

        trade.stopLoss = 0  # No SL
        trade.target = 0  # setting to 0 as no target is applicable for this trade

        trade.intradaySquareOffTimestamp = Utils.getEpoch(self.squareOffTimestamp)
        # Hand over the trade to TradeManager
        TradeManager.addNewTrade(trade)

    def shouldPlaceTrade(self, trade, tick):
        # First call base class implementation and if it returns True then only proceed
        if super().shouldPlaceTrade(trade, tick) == False:
            return False
        # We dont have any condition to be checked here for this strategy just return True
        return True

    def getTrailingSL(self, trade):
        if trade == None:
            return 0
        if trade.entry == 0:
            return 0
        lastTradedPrice = TradeManager.getLastTradedPrice(trade.tradingSymbol)
        if lastTradedPrice == 0:
            return 0

        trailSL = 0
        profitPointsPer = ((trade.entry - lastTradedPrice) / trade.entry) * 100
        if profitPointsPer >= 10:  # 10% Move
            factor = (floor(profitPointsPer / 10)) * 5  # 5% SL
            trailSL = Utils.roundToNSEPrice(trade.initialStopLoss - (factor * trade.initialStopLoss / 100))

        # trailSL = 0
        # profitPoints = int(trade.entry - lastTradedPrice)
        # if profitPoints >= 5:
        #   factor = int(profitPoints / 5)
        #   trailSL = Utils.roundToNSEPrice(trade.initialStopLoss - factor * 5)

        # logging.info('%s: %s Returning trail SL %f', self.getName(), trade.tradingSymbol, trailSL)
        if (trade.tsl == 0):
            trade.tsl = trailSL
        if (trailSL < trade.tsl and trade.tsl != 0):
            trade.tsl = trailSL
            logging.info('%s: %s Returning trail SL %f', self.getName(), trade.tradingSymbol, trade.tsl)
            return trailSL
        else:
            logging.info('%s: %s Returning trail SL %f', self.getName(), trade.tradingSymbol, trade.tsl)
            return trade.tsl

    def lockAndTrailPNL(self):
        if (self.strategyTSL == True):
            strategypnl = TradeManager.getStrategyPNL(self.getName())
            logging.info('%s:Returning Strategy PNL %f %f', self.getName(), strategypnl, self.strategySL)
            if (strategypnl <= self.strategySL):
                return bool(1)
            elif strategypnl > self.strategyTGT:
                # if floor(strategypnl - self.strategyTGT) > self.strategyTrailPLInc:
                temppnl = int(self.strategyTGTlock + ((floor((strategypnl - self.strategyTGT)
                                                             / self.strategyTrailPLInc)) * self.strategyTrailPLstep))
                if (self.strategySL < temppnl):
                    self.strategySL = temppnl

                return bool(0)
            return (bool(0))

    def passStrategySL(self):
        return self.strategySL

    @staticmethod
    def isWithinTradingRange(low):
        if (low >= 5.00 and low <= 10.00):
            return True
        else:
            return False

import logging
import threading
import time

from instruments.Instruments import Instruments
from strategies.MyStraddleStrangleHedge import ShortStraddleStrangleBNFhedge
from trademgmt.TradeManager import TradeManager


# from Test import Test

class Algo:
  isAlgoRunning = None

  @staticmethod
  def startAlgo():
    if Algo.isAlgoRunning == True:
      logging.info("Algo has already started..")
      return
    
    logging.info("Starting Algo...")
    Instruments.fetchInstruments()

    # start trade manager in a separate thread
    tm = threading.Thread(target=TradeManager.run)
    tm.start()

    # sleep for 2 seconds for TradeManager to get initialized
    time.sleep(2)

    # start running strategies: Run each strategy in a separate thread
    # threading.Thread(target=SampleStrategy.getInstance().run).start()
    # threading.Thread(target=BNFORB30Min.getInstance().run).start()
    # threading.Thread(target=OptionSelling.getInstance().run).start()
    # threading.Thread(target=ShortStraddleStrangleBNF.getInstance().run).start()
    threading.Thread(target=ShortStraddleStrangleBNFhedge.getInstance().run).start()
    # threading.Thread(target=indexTicker.run).start()

    Algo.isAlgoRunning = True
    logging.info("Algo started.")

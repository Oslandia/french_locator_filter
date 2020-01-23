# -*- coding: utf-8 -*-

from qgis.core import Qgis, QgsMessageLog, QgsLocatorFilter, QgsLocatorResult, QgsRectangle, QgsPointXY, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject

from . networkaccessmanager import NetworkAccessManager, RequestsException

from qgis.PyQt.QtCore import pyqtSignal

import json


class LocatorFilterPlugin:

    def __init__(self, iface):

        self.iface = iface

        self.filter = locatorFilter(self.iface)

        self.filter.resultProblem.connect(self.show_problem)
        self.iface.registerLocatorFilter(self.filter)

    def show_problem(self, err):
        self.iface.messageBar().pushWarning("French Locator Filter Error", '{}'.format(err))

    def initGui(self):
        pass

    def unload(self):
        self.iface.deregisterLocatorFilter(self.filter)


class locatorFilter(QgsLocatorFilter):

    USER_AGENT = b'Mozilla/5.0 QGIS LocatorFilter'

    SEARCH_URL = 'https://api-adresse.data.gouv.fr/search/?limit=10&autocomplete=1&q='
    
    resultProblem = pyqtSignal(str)

    def __init__(self, iface):
        self.iface = iface
        super(QgsLocatorFilter, self).__init__()

    def name(self):
        return self.__class__.__name__

    def clone(self):
        return locatorFilter(self.iface)

    def displayName(self):
        return u'Géocodeur API Adresse FR'

    def prefix(self):
        return 'fra'

    def fetchResults(self, search, context, feedback):

        if len(search) < 2:
            return

        url = '{}{}'.format(self.SEARCH_URL, search)
        self.info('Search url {}'.format(url))
        nam = NetworkAccessManager()
        try:
            
            headers = {b'User-Agent': self.USER_AGENT}
            # use BLOCKING request, as fetchResults already has it's own thread!
            (response, content) = nam.request(url, headers=headers, blocking=True)
            
            if response.status_code == 200:  # other codes are handled by NetworkAccessManager
                content_string = content.decode('utf-8')
                locations = json.loads(content_string)
                
                #loop on features in json collection
                for loc in locations['features']: 

                    result = QgsLocatorResult()
                    result.filter = self
                    label = loc['properties']['label']
                    if loc['properties']['type'] == 'municipality':
                        # add city code to label
                        label += ' ' + loc['properties']['citycode']
                    result.displayString = '{} ({})'.format(label, loc['properties']['type'])
                    #use the json full item as userData, so all info is in it:
                    result.userData = loc
                    self.resultFetched.emit(result)

        except RequestsException as err:
            # Handle exception..
            self.info(err)
            self.resultProblem.emit('{}'.format(err))


    def triggerResult(self, result):
        self.info("UserClick: {}".format(result.displayString))
        doc = result.userData
        x = doc['geometry']['coordinates'][0]
        y = doc['geometry']['coordinates'][1]
  
        centerPoint = QgsPointXY(x, y)

        dest_crs = QgsProject.instance().crs()
        results_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.PostgisCrsId)
        aTransform = QgsCoordinateTransform(results_crs, dest_crs, QgsProject.instance())
        centerPointProjected = aTransform.transform(centerPoint)
        aTransform.transform(centerPoint)
        
        #centers to adress coordinates
        self.iface.mapCanvas().setCenter(centerPointProjected)

        # zoom policy has we don't have extent in the results       
        scale = 25000
        
        type_adress = doc['properties']['type']

        if type_adress == 'housenumber' : 
            scale = 2000
        elif  type_adress == 'street' :    
            scale = 5000
        elif  type_adress == 'locality' :    
            scale = 5000

        # finally zoom actually
        self.iface.mapCanvas().zoomScale(scale)
        self.iface.mapCanvas().refresh()

    def info(self, msg=""):
        QgsMessageLog.logMessage('{} {}'.format(self.__class__.__name__, msg), 'LocatorFilter', Qgis.Info)

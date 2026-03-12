# Transport API Integration (TfL)

**Service:** Transport for London (TfL) Unified API
**Cost:** FREE
**Coverage:** London and surrounding areas
**Docs:** https://api.tfl.gov.uk/

## Why Transport Data Matters for Property Investment

| Metric | Importance |
|--------|------------|
| **Nearest Station** | Tenant #1 priority |
| **Journey Time to City** | Determines rental demand |
| **Tube vs Rail vs Bus** | Affects property value |
| **Night Tube/24hr** | Premium for shift workers |
| **Commute Zones** | Zone 1-6 pricing tiers |

## API Credentials

```
App ID: afcaf66b
App Key: 01143ec72ae2c8e4c3aa631e5f27b845
```

## Key Endpoints

Base URL: `https://api.tfl.gov.uk/`

### 1. Find Nearest Stations
```
GET /StopPoint?lat={LAT}&lon={LON}&stopTypes=NaptanMetroStation,NaptanRailStation&radius=1000
```

### 2. Journey Planner
```
GET /Journey/JourneyResults/{FROM}/to/{TO}?app_id={ID}&app_key={KEY}
```

### 3. Station Arrivals
```
GET /StopPoint/{STATION_ID}/Arrivals
```

### 4. Line Status
```
GET /Line/Mode/tube/Status
```

## Python Integration

```python
import requests
import os
from typing import List, Dict

TFL_APP_ID = "afcaf66b"
TFL_APP_KEY = "01143ec72ae2c8e4c3aa631e5f27b845"
TFL_BASE_URL = "https://api.tfl.gov.uk"

class TransportAPI:
    """Transport for London API Client"""
    
    def __init__(self, app_id=None, app_key=None):
        self.app_id = app_id or TFL_APP_ID
        self.app_key = app_key or TFL_APP_KEY
        self.base_url = TFL_BASE_URL
    
    def _make_request(self, endpoint, params=None):
        """Make authenticated request to TfL API"""
        url = f"{self.base_url}/{endpoint}"
        
        # Add auth params
        params = params or {}
        params['app_id'] = self.app_id
        params['app_key'] = self.app_key
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {'error': str(e)}
    
    def get_nearest_stations(self, lat, lon, radius=1000):
        """
        Find nearest tube/rail stations to coordinates
        
        Args:
            lat: Latitude
            lon: Longitude
            radius: Search radius in meters (default 1000m)
            
        Returns:
            List of nearby stations
        """
        endpoint = "StopPoint"
        params = {
            'lat': lat,
            'lon': lon,
            'stopTypes': 'NaptanMetroStation,NaptanRailStation,NaptanPublicBusCoachTram',
            'radius': radius,
            'returnLines': 'true'
        }
        
        data = self._make_request(endpoint, params)
        
        stations = []
        for stop in data.get('stopPoints', []):
            station = {
                'name': stop.get('commonName'),
                'id': stop.get('id'),
                'distance': stop.get('distance'),
                'modes': stop.get('modes', []),
                'lines': [line.get('name') for line in stop.get('lines', [])],
                'lat': stop.get('lat'),
                'lon': stop.get('lon')
            }
            stations.append(station)
        
        # Sort by distance
        stations.sort(key=lambda x: x.get('distance', 9999))
        return stations
    
    def get_journey_time(self, from_postcode, to_postcode):
        """
        Get journey time between two postcodes
        
        Args:
            from_postcode: Starting postcode
            to_postcode: Destination postcode
            
        Returns:
            Journey details including duration
        """
        endpoint = f"Journey/JourneyResults/{from_postcode}/to/{to_postcode}"
        data = self._make_request(endpoint)
        
        if 'journeys' in data and len(data['journeys']) > 0:
            journey = data['journeys'][0]
            return {
                'duration_minutes': journey.get('duration'),
                'arrival_time': journey.get('arrivalDateTime'),
                'modes': [leg.get('mode', {}).get('name') for leg in journey.get('legs', [])],
                'fare': journey.get('fare', {}).get('totalCost')
            }
        return None
    
    def get_station_arrivals(self, station_id):
        """Get live arrivals for a station"""
        endpoint = f"StopPoint/{station_id}/Arrivals"
        return self._make_request(endpoint)
    
    def get_line_status(self):
        """Get current tube line status"""
        endpoint = "Line/Mode/tube/Status"
        return self._make_request(endpoint)

# Global instance
transport_api = TransportAPI()
```

## Sample Response - Nearest Stations

```json
{
  "stopPoints": [
    {
      "commonName": "Manchester Piccadilly Station",
      "distance": 450,
      "modes": ["train"],
      "lines": [
        {"name": "Northern"},
        {"name": "TransPennine Express"}
      ],
      "lat": 53.4773,
      "lon": -2.2301
    },
    {
      "commonName": "Piccadilly Gardens",
      "distance": 520,
      "modes": ["bus", "tram"],
      "lines": [
        {"name": "Metrolink"}
      ]
    }
  ]
}
```

## Usage Examples

```python
from transport_api import transport_api

# Find stations near a property
stations = transport_api.get_nearest_stations(53.4773, -2.2301)
for station in stations[:3]:
    print(f"{station['name']}: {station['distance']}m - {', '.join(station['lines'])}")

# Check commute to city center
journey = transport_api.get_journey_time("M1 1AA", "EC2N 1AR")
print(f"Commute time: {journey['duration_minutes']} minutes")
```

## Limitations

- **Coverage:** London + surrounding areas best
- **Postcodes:** Some UK postcodes outside London may not work
- **Rate Limits:** 500 requests/minute (very generous)
- **Real-time:** Live arrivals, journey planning

## Integration with Deal Analyzer

Add to property analysis:
```python
def analyze_transport(postcode, lat, lon):
    stations = transport_api.get_nearest_stations(lat, lon)
    
    analysis = {
        'nearest_station': stations[0]['name'] if stations else None,
        'station_distance': stations[0]['distance'] if stations else None,
        'transport_score': calculate_score(stations),
        'commute_time_to_city': get_city_commute(postcode)
    }
    
    return analysis
```

## Scoring System

| Distance to Station | Score | Impact |
|---------------------|-------|--------|
| < 500m | 10/10 | Excellent |
| 500m - 1km | 8/10 | Good |
| 1km - 2km | 6/10 | Acceptable |
| 2km+ | 3/10 | Poor |

**Transport Score affects:**
- Rental demand estimate
- Property valuation
- Investment attractiveness

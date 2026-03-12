# National Rail API Integration (UK-Wide)

**Service:** National Rail Enquiries (NRE) / RealTime Trains
**Cost:** FREE tier available
**Coverage:** Entire UK rail network
**Best for:** Properties outside London

## Why National Rail API

| Feature | TfL API | National Rail |
|---------|---------|---------------|
| Coverage | London only | **UK-wide** ✅ |
| Data | Tube + Rail | **All UK trains** ✅ |
| Stations | 270+ | **2,500+** ✅ |
| Manchester, Birmingham, etc. | ❌ No | ✅ Yes |

## API Options

### Option 1: RealTime Trains (Recommended)
- **URL:** https://api.rtt.io/
- **Free tier:** 100 requests/day
- **Paid tier:** £10/month for 10,000 requests
- **Data:** Live departures, station info, journeys

### Option 2: National Rail Enquiries (Darwin)
- **URL:** https://lite.realtime.nationalrail.co.uk/
- **Cost:** FREE (registration required)
- **Data:** Live train info, delays, platform numbers

### Option 3: TransportAPI (Unified)
- **URL:** https://www.transportapi.com/
- **Free tier:** 1,000 requests/day
- **Coverage:** Bus + Rail + Metro UK-wide

## RealTime Trains Setup

### 1. Get API Credentials
```
Website: https://api.rtt.io/
Sign up → Get credentials:
- Username: (your email)
- Password: (API token)
```

### 2. Authentication
RealTime Trains uses HTTP Basic Auth:
```python
import requests
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth('username', 'password')
response = requests.get(url, auth=auth)
```

## Key Endpoints

### Find Nearest Station
```
GET https://api.rtt.io/api/v1/json/search/{STATION_CODE}
```

### Station Information
```
GET https://api.rtt.io/api/v1/json/station/{STATION_CODE}
```

### Journey Planning
```
GET https://api.rtt.io/api/v1/json/service/{SERVICE_UID}
```

## Python Integration

```python
import requests
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Optional
import os

RTT_USERNAME = os.getenv('RTT_USERNAME', 'your_email@example.com')
RTT_PASSWORD = os.getenv('RTT_PASSWORD', 'your_api_token')
RTT_BASE_URL = "https://api.rtt.io/api/v1/json"

class NationalRailAPI:
    """National Rail / RealTime Trains API Client"""
    
    def __init__(self, username=None, password=None):
        self.username = username or RTT_USERNAME
        self.password = password or RTT_PASSWORD
        self.base_url = RTT_BASE_URL
        self.auth = HTTPBasicAuth(self.username, self.password)
    
    def get_station_info(self, station_code: str) -> Dict:
        """Get information about a station"""
        url = f"{self.base_url}/station/{station_code}"
        response = requests.get(url, auth=self.auth)
        return response.json()
    
    def get_live_departures(self, station_code: str) -> Dict:
        """Get live departures from a station"""
        url = f"{self.base_url}/station/{station_code}/departures"
        response = requests.get(url, auth=self.auth)
        return response.json()
    
    def find_stations_near_postcode(self, postcode: str, radius_km: int = 5) -> List[Dict]:
        """
        Find rail stations near a postcode
        (Uses postcode.io API first to get coordinates)
        """
        # Get coordinates from postcode
        pc_response = requests.get(f"https://api.postcodes.io/postcodes/{postcode}")
        if pc_response.status_code != 200:
            return []
        
        data = pc_response.json()
        if 'result' not in data:
            return []
        
        lat = data['result']['latitude']
        lon = data['result']['longitude']
        
        # Find nearby stations using TransportAPI (free tier)
        transport_url = "https://transportapi.com/v3/uk/places.json"
        params = {
            'lat': lat,
            'lon': lon,
            'type': 'train_station',
            'app_id': os.getenv('TRANSPORTAPI_APP_ID'),
            'app_key': os.getenv('TRANSPORTAPI_KEY')
        }
        
        response = requests.get(transport_url, params=params)
        if response.status_code == 200:
            return response.json().get('member', [])
        
        return []

# Global instance
national_rail = NationalRailAPI()
```

## Alternative: Simple Station Lookup (No API Key)

For basic functionality without API registration:

```python
import requests
import math

# List of major UK stations with coordinates
MAJOR_STATIONS = {
    'MAN': {'name': 'Manchester Piccadilly', 'lat': 53.4773, 'lon': -2.2301},
    'BHM': {'name': 'Birmingham New Street', 'lat': 52.4776, 'lon': -1.8991},
    'LDS': {'name': 'Leeds', 'lat': 53.7959, 'lon': -1.5494},
    'LIV': {'name': 'Liverpool Lime Street', 'lat': 53.4073, 'lon': -2.9778},
    'SHF': {'name': 'Sheffield', 'lat': 53.3782, 'lon': -1.4620},
    'BRI': {'name': 'Bristol Temple Meads', 'lat': 51.4491, 'lon': -2.5803},
    # ... add more as needed
}

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in km"""
    R = 6371  # Earth's radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def get_nearest_major_station(lat, lon):
    """Find nearest major station (no API needed)"""
    nearest = None
    min_distance = float('inf')
    
    for code, station in MAJOR_STATIONS.items():
        dist = haversine_distance(lat, lon, station['lat'], station['lon'])
        if dist < min_distance:
            min_distance = dist
            nearest = {**station, 'code': code, 'distance_km': dist}
    
    return nearest
```

## Station Database Integration

Create a local database of UK stations:

```python
# stations.py - Static data for common stations
UK_STATIONS = {
    # Manchester area
    'Manchester': [
        {'name': 'Manchester Piccadilly', 'code': 'MAN', 'lat': 53.4773, 'lon': -2.2301},
        {'name': 'Manchester Victoria', 'code': 'MCV', 'lat': 53.4875, 'lon': -2.2426},
        {'name': 'Manchester Oxford Road', 'code': 'MCO', 'lat': 53.4710, 'lon': -2.2423},
    ],
    # Add more cities...
}

def find_nearest_station(postcode: str, city: str = None) -> Dict:
    """Find nearest station by postcode or city"""
    # Implementation here
    pass
```

## Usage Example

```python
from national_rail import get_nearest_major_station

# Coordinates for OL7 0DA
lat, lon = 53.4890, -2.0947

station = get_nearest_major_station(lat, lon)
print(f"Nearest major station: {station['name']}")
print(f"Distance: {station['distance_km']:.1f}km")
print(f"Station code: {station['code']}")
```

## Coverage Comparison

| City | Nearest Major Station | Distance from OL7 0DA |
|------|----------------------|----------------------|
| Manchester | Piccadilly | ~8km |
| Ashton-under-Lyne | Ashton | ~2km |
| Stalybridge | Stalybridge | ~4km |

## Integration with Deal Analyzer

```python
def analyze_transport_national(postcode, lat, lon):
    """UK-wide transport analysis"""
    
    # Get nearest major station
    station = get_nearest_major_station(lat, lon)
    
    if station:
        distance = station['distance_km']
        
        # Score based on distance
        if distance < 1:
            score = 9
            rating = 'Excellent'
        elif distance < 2:
            score = 8
            rating = 'Very Good'
        elif distance < 5:
            score = 7
            rating = 'Good'
        elif distance < 10:
            score = 6
            rating = 'Acceptable'
        else:
            score = 4
            rating = 'Poor'
        
        return {
            'score': score,
            'rating': rating,
            'nearest_station': station['name'],
            'station_code': station['code'],
            'distance_km': round(distance, 1),
            'journey_time_to_major_city': 'N/A (requires API)'
        }
    
    return {'score': 0, 'rating': 'Unknown', 'nearest_station': None}
```

## Next Steps

1. **Sign up** for RealTime Trains API: https://api.rtt.io/
2. **Get credentials** (username = email, password = token)
3. **Set environment variables:**
   ```bash
   export RTT_USERNAME="your_email@example.com"
   export RTT_PASSWORD="your_api_token"
   ```
4. **Test integration** with Manchester postcodes

## Rate Limits

- **RealTime Trains Free:** 100 requests/day
- **TransportAPI Free:** 1,000 requests/day
- **National Rail Darwin:** 5,000 requests/hour

**Recommendation:** Use the simple distance calculation (no API) for basic scoring, upgrade to RealTime Trains for detailed journey data.

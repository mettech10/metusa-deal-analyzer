"""
National Rail / UK-Wide Transport API Integration
Provides train station data for properties outside London
"""

import requests
import math
import os
from typing import List, Dict, Optional
from dataclasses import dataclass

# Major UK stations database (coordinates from Wikipedia/OpenStreetMap)
MAJOR_STATIONS = {
    # Manchester area
    'Manchester Piccadilly': {'code': 'MAN', 'lat': 53.4773, 'lon': -2.2301, 'city': 'Manchester'},
    'Manchester Victoria': {'code': 'MCV', 'lat': 53.4875, 'lon': -2.2426, 'city': 'Manchester'},
    'Manchester Oxford Road': {'code': 'MCO', 'lat': 53.4710, 'lon': -2.2423, 'city': 'Manchester'},
    
    # Ashton area (near OL7)
    'Ashton-under-Lyne': {'code': 'AHN', 'lat': 53.4903, 'lon': -2.0935, 'city': 'Ashton-under-Lyne'},
    'Stalybridge': {'code': 'SYB', 'lat': 53.4846, 'lon': -2.0620, 'city': 'Stalybridge'},
    
    # Birmingham
    'Birmingham New Street': {'code': 'BHM', 'lat': 52.4776, 'lon': -1.8991, 'city': 'Birmingham'},
    'Birmingham Moor Street': {'code': 'BMO', 'lat': 52.4791, 'lon': -1.8925, 'city': 'Birmingham'},
    
    # Leeds
    'Leeds': {'code': 'LDS', 'lat': 53.7959, 'lon': -1.5494, 'city': 'Leeds'},
    
    # Liverpool
    'Liverpool Lime Street': {'code': 'LIV', 'lat': 53.4073, 'lon': -2.9778, 'city': 'Liverpool'},
    
    # Sheffield
    'Sheffield': {'code': 'SHF', 'lat': 53.3782, 'lon': -1.4620, 'city': 'Sheffield'},
    
    # Bristol
    'Bristol Temple Meads': {'code': 'BRI', 'lat': 51.4491, 'lon': -2.5803, 'city': 'Bristol'},
    
    # Newcastle
    'Newcastle': {'code': 'NCL', 'lat': 54.9683, 'lon': -1.6170, 'city': 'Newcastle'},
    
    # Glasgow
    'Glasgow Central': {'code': 'GLC', 'lat': 55.8590, 'lon': -4.2580, 'city': 'Glasgow'},
    
    # Edinburgh
    'Edinburgh Waverley': {'code': 'EDB', 'lat': 55.9521, 'lon': -3.1903, 'city': 'Edinburgh'},
    
    # Cardiff
    'Cardiff Central': {'code': 'CDF', 'lat': 51.4759, 'lon': -3.1791, 'city': 'Cardiff'},
    
    # Nottingham
    'Nottingham': {'code': 'NOT', 'lat': 52.9471, 'lon': -1.1472, 'city': 'Nottingham'},
    
    # Leicester
    'Leicester': {'code': 'LEI', 'lat': 52.6314, 'lon': -1.1252, 'city': 'Leicester'},
    
    # Coventry
    'Coventry': {'code': 'COV', 'lat': 52.4008, 'lon': -1.5135, 'city': 'Coventry'},
    
    # Reading
    'Reading': {'code': 'RDG', 'lat': 51.4592, 'lon': -0.9716, 'city': 'Reading'},
    
    # Oxford
    'Oxford': {'code': 'OXF', 'lat': 51.7535, 'lon': -1.2700, 'city': 'Oxford'},
    
    # Cambridge
    'Cambridge': {'code': 'CBG', 'lat': 52.1940, 'lon': 0.1372, 'city': 'Cambridge'},
}

@dataclass
class Station:
    """Represents a UK train station"""
    name: str
    code: str
    lat: float
    lon: float
    distance_km: float
    city: str

class NationalRailAPI:
    """
    UK-wide National Rail API client
    Uses station database + postcode.io for coordinates
    No API key required for basic distance calculations
    """
    
    def __init__(self):
        self.stations = MAJOR_STATIONS
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in km"""
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _get_postcode_coordinates(self, postcode: str) -> Optional[tuple]:
        """Get lat/lon from postcode using postcode.io (free)"""
        try:
            url = f"https://api.postcodes.io/postcodes/{postcode.replace(' ', '')}"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if 'result' in data:
                    return (data['result']['latitude'], data['result']['longitude'])
        except Exception as e:
            print(f"Error getting postcode coordinates: {e}")
        
        return None
    
    def get_nearest_stations(self, lat: float, lon: float, limit: int = 5) -> List[Station]:
        """
        Find nearest stations to coordinates
        
        Args:
            lat: Latitude
            lon: Longitude
            limit: Maximum number of stations to return
            
        Returns:
            List of Station objects sorted by distance
        """
        stations_with_distance = []
        
        for name, data in self.stations.items():
            distance = self._haversine_distance(
                lat, lon,
                data['lat'], data['lon']
            )
            
            station = Station(
                name=name,
                code=data['code'],
                lat=data['lat'],
                lon=data['lon'],
                distance_km=distance,
                city=data.get('city', 'Unknown')
            )
            stations_with_distance.append(station)
        
        # Sort by distance
        stations_with_distance.sort(key=lambda x: x.distance_km)
        
        return stations_with_distance[:limit]
    
    def get_nearest_station_by_postcode(self, postcode: str) -> Optional[Station]:
        """
        Find nearest station to a UK postcode
        
        Args:
            postcode: UK postcode (e.g., "OL7 0DA")
            
        Returns:
            Nearest Station or None if postcode invalid
        """
        coords = self._get_postcode_coordinates(postcode)
        if not coords:
            return None
        
        lat, lon = coords
        stations = self.get_nearest_stations(lat, lon, limit=1)
        
        return stations[0] if stations else None
    
    def calculate_transport_score(self, distance_km: float) -> Dict:
        """
        Calculate transport connectivity score
        
        Args:
            distance_km: Distance to nearest station in km
            
        Returns:
            Dict with score and rating
        """
        if distance_km < 1:
            score = 10
            rating = 'Excellent'
        elif distance_km < 2:
            score = 9
            rating = 'Very Good'
        elif distance_km < 5:
            score = 7
            rating = 'Good'
        elif distance_km < 10:
            score = 6
            rating = 'Acceptable'
        elif distance_km < 15:
            score = 4
            rating = 'Poor'
        else:
            score = 2
            rating = 'Very Poor'
        
        return {
            'score': score,
            'rating': rating,
            'distance_km': round(distance_km, 1),
            'walk_time_min': round(distance_km * 12)  # ~5km/h walking speed
        }
    
    def get_transport_summary(self, postcode: str = None, lat: float = None, lon: float = None) -> Dict:
        """
        Get complete transport summary
        
        Args:
            postcode: UK postcode (optional if lat/lon provided)
            lat: Latitude (optional if postcode provided)
            lon: Longitude (optional if postcode provided)
            
        Returns:
            Complete transport analysis
        """
        # Get coordinates
        if postcode and not (lat and lon):
            coords = self._get_postcode_coordinates(postcode)
            if coords:
                lat, lon = coords
            else:
                return {
                    'error': 'Could not find coordinates for postcode',
                    'score': 0,
                    'rating': 'Unknown'
                }
        
        if not (lat and lon):
            return {
                'error': 'Need postcode or lat/lon coordinates',
                'score': 0,
                'rating': 'Unknown'
            }
        
        # Get nearest stations
        stations = self.get_nearest_stations(lat, lon, limit=3)
        
        if not stations:
            return {
                'error': 'No stations found',
                'score': 0,
                'rating': 'Unknown'
            }
        
        # Calculate score based on nearest
        nearest = stations[0]
        score_data = self.calculate_transport_score(nearest.distance_km)
        
        # Format top stations
        top_stations = []
        for station in stations:
            top_stations.append({
                'name': station.name,
                'code': station.code,
                'distance_km': round(station.distance_km, 1),
                'city': station.city
            })
        
        return {
            'connectivity_score': score_data,
            'nearest_stations': top_stations,
            'summary': f"{score_data['rating']} rail connectivity. "
                      f"Nearest: {nearest.name} "
                      f"({nearest.distance_km:.1f}km, ~{score_data['walk_time_min']}min walk). "
                      f"Located in {nearest.city} area."
        }

# Global instance
national_rail = NationalRailAPI()

# Helper function for deal analysis
def get_national_rail_context(postcode: str) -> Dict:
    """
    Get rail transport context for deal analysis
    
    Args:
        postcode: UK postcode
        
    Returns:
        Transport analysis for AI
    """
    try:
        return national_rail.get_transport_summary(postcode=postcode)
    except Exception as e:
        return {'error': str(e), 'score': 0, 'rating': 'Unknown'}

if __name__ == "__main__":
    # Test the API
    print("🚂 Testing National Rail API...")
    
    # Test with OL7 0DA
    postcode = "OL7 0DA"
    print(f"\n📍 Testing with postcode: {postcode}")
    print("="*50)
    
    result = get_national_rail_context(postcode)
    
    if 'error' in result:
        print(f"❌ Error: {result['error']}")
    else:
        print(f"\n📊 Transport Score: {result['connectivity_score']['score']}/10")
        print(f"Rating: {result['connectivity_score']['rating']}")
        print(f"Distance: {result['connectivity_score']['distance_km']}km")
        print(f"Walk time: ~{result['connectivity_score']['walk_time_min']} minutes")
        
        print(f"\n🚉 Nearest Stations:")
        for station in result['nearest_stations']:
            print(f"  • {station['name']} ({station['code']}): {station['distance_km']}km")
        
        print(f"\n📝 Summary:")
        print(f"  {result['summary']}")
    
    # Test with London postcode
    print("\n" + "="*50)
    postcode = "E1 6AN"  # Shoreditch
    print(f"\n📍 Testing with postcode: {postcode}")
    
    result = get_national_rail_context(postcode)
    if 'error' not in result:
        print(f"Score: {result['connectivity_score']['score']}/10")
        print(f"Nearest: {result['nearest_stations'][0]['name']}")
    
    print("\n✅ Test complete!")

import streamlit as st
import pandas as pd
import numpy as np
from shapely.geometry import Polygon
from sklearn.cluster import DBSCAN
from scipy.spatial import ConvexHull
import folium
from folium import plugins
from geopy.distance import geodesic
import requests
from datetime import datetime, timedelta
import time

# Function to fetch data from the API
def fetch_data(vehicle, start_time, end_time):
    API_KEY = "3330d953-7abc-4bac-b862-ac315c8e2387-6252fa58-d2c2-4c13-b23e-59cefafa4d7d"
    url = f"https://admintestapi.ensuresystem.in/api/locationpull/orbit?vehicle={vehicle}&from={start_time}&to={end_time}"
    headers = {"token": API_KEY}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        st.error(f"Error fetching data: {response.status_code}")
        return None

    data = response.json()
    if not isinstance(data, list):
        st.error(f"Unexpected data format: {data}")
        return None
    
    # Sort data by time
    data.sort(key=lambda x: x['time'])
    return data

# Function to calculate the area of a field in square meters using convex hull
def calculate_convex_hull_area(points):
    if len(points) < 3:  # Not enough points to form a polygon
        return 0
    try:
        hull = ConvexHull(points)
        poly = Polygon(points[hull.vertices])
        return poly.area  # Area in square degrees
    except Exception:
        return 0

# Function to calculate centroid of a set of points
def calculate_centroid(points):
    return np.mean(points, axis=0)

# Function to generate more points along the convex hull
def generate_more_hull_points(points, num_splits=3):
    new_points = []
    for i in range(len(points)):
        start_point = points[i]
        end_point = points[(i + 1) % len(points)]
        new_points.append(start_point)
        for j in range(1, num_splits):
            intermediate_point = start_point + j * (end_point - start_point) / num_splits
            new_points.append(intermediate_point)
    return np.array(new_points)

# Function to generate a Google Maps link for the latest location
def get_latest_location_link(lat, lon):
    # Generate a Google Maps link for navigation
    gmap_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    return gmap_link

# Function to fetch real-time data from the API
def fetch_latest_data(vehicle):
    API_KEY = "3330d953-7abc-4bac-b862-ac315c8e2387-6252fa58-d2c2-4c13-b23e-59cefafa4d7d"
    end_time = int(datetime.now().timestamp() * 1000)  # Current timestamp in milliseconds
    start_time = end_time - (60 * 1000)  # Fetch data from the last minute
    
    url = f"https://admintestapi.ensuresystem.in/api/locationpull/orbit?vehicle={vehicle}&from={start_time}&to={end_time}"
    headers = {"token": API_KEY}
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        st.error(f"Error fetching data: {response.status_code}")
        return None

    data = response.json()
    if not isinstance(data, list) or not data:
        st.error("No real-time data available.")
        return None
    
    # Sort data by time and return the most recent data point
    data.sort(key=lambda x: x['time'])
    latest_point = data[-1]  # Latest location data point
    return latest_point

# Streamlit app for real-time location tracking
def main():
    st.title("Real-Time Vehicle Location")

    # Input for vehicle ID
    vehicle = st.text_input("Enter Vehicle ID:")

    if vehicle:
        if st.button("Track Real-Time Location"):
            st.write("Fetching real-time location...")

            while True:
                latest_data = fetch_latest_data(vehicle)

                if latest_data:
                    lat = latest_data['lat']
                    lon = latest_data['lon']
                    timestamp = datetime.fromtimestamp(latest_data['time'] / 1000).strftime('%Y-%m-%d %H:%M:%S')

                    gmap_link = get_latest_location_link(lat, lon)

                    # Display the latest location and Google Maps link
                    st.write(f"Latest Location (Lat: {lat}, Lng: {lon}) at {timestamp}")
                    st.write(f"[Navigate to Real-Time Location]({gmap_link})")

                # Wait for 15 seconds before fetching the next location
                time.sleep(15)

                # Rerun the script to update the latest location
                st.experimental_rerun()

if __name__ == "__main__":
    main()

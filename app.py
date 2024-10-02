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
import os

# Function to fetch data from the API
def fetch_data(vehicle, start_time, end_time):
    API_KEY = "3330d953-7abc-4bac-b862-ac315c8e2387-6252fa58-d2c2-4c13-b23e-59cefafa4d7d"
    url = f"https://admintestapi.ensuresystem.in/api/locationpull/orbit?vehicle={vehicle}&from={start_time}&to={end_time}"
    headers = {"token": API_KEY}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching data: {e}")
        return None

    try:
        data = response.json()
    except ValueError:
        st.error("Error parsing JSON response.")
        return None
    
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

# Function to process the fetched data and return the map and field areas
def process_data(data, show_hull_points):
    # Create a DataFrame from the fetched data
    gps_data = pd.DataFrame(data)
    gps_data['Timestamp'] = pd.to_datetime(gps_data['time'], unit='ms')
    gps_data['lat'] = gps_data['lat']
    gps_data['lng'] = gps_data['lon']
    
    # Cluster the GPS points to identify separate fields
    coords = gps_data[['lat', 'lng']].values
    db = DBSCAN(eps=0.0001, min_samples=11).fit(coords)
    labels = db.labels_

    # Add labels to the data
    gps_data['field_id'] = labels

    # Calculate the area for each field
    fields = gps_data[gps_data['field_id'] != -1]  # Exclude noise points
    field_areas = fields.groupby('field_id').apply(
        lambda df: calculate_convex_hull_area(df[['lat', 'lng']].values)
    )

    # Convert the area from square degrees to square meters (approximation)
    field_areas_m2 = field_areas * 0.77 * (111000 ** 2)  # rough approximation

    # Convert the area from square meters to gunthas (1 guntha = 101.17 m^2)
    field_areas_gunthas = field_areas_m2 / 101.17

    # Calculate time metrics for each field
    field_times = fields.groupby('field_id').apply(
        lambda df: (df['Timestamp'].max() - df['Timestamp'].min()).total_seconds() / 60.0
    )

    # Extract start and end dates for each field
    field_dates = fields.groupby('field_id').agg(
        start_date=('Timestamp', 'min'),
        end_date=('Timestamp', 'max')
    )

    # Filter out fields with area less than 5 gunthas
    valid_fields = field_areas_gunthas[field_areas_gunthas >= 5].index
    field_areas_gunthas = field_areas_gunthas[valid_fields]
    field_times = field_times[valid_fields]
    field_dates = field_dates.loc[valid_fields]

    # Calculate centroids of each field
    centroids = fields.groupby('field_id').apply(
        lambda df: calculate_centroid(df[['lat', 'lng']].values)
    )

    # Calculate traveling distance and time between field centroids
    travel_distances = []
    travel_times = []
    field_ids = list(valid_fields)
    
    if len(field_ids) > 1:
        for i in range(len(field_ids) - 1):
            centroid1 = centroids.loc[field_ids[i]]
            centroid2 = centroids.loc[field_ids[i + 1]]
            distance = geodesic(centroid1, centroid2).kilometers
            time = (field_dates.loc[field_ids[i + 1], 'start_date'] - field_dates.loc[field_ids[i], 'end_date']).total_seconds() / 60.0
            travel_distances.append(distance)
            travel_times.append(time)

        # Calculate distance from last point of one field to first point of the next field
        for i in range(len(field_ids) - 1):
            end_point = fields[fields['field_id'] == field_ids[i]][['lat', 'lng']].values[-1]
            start_point = fields[fields['field_id'] == field_ids[i + 1]][['lat', 'lng']].values[0]
            distance = geodesic(end_point, start_point).kilometers
            time = (field_dates.loc[field_ids[i + 1], 'start_date'] - field_dates.loc[field_ids[i], 'end_date']).total_seconds() / 60.0
            travel_distances.append(distance)
            travel_times.append(time)

        # Append NaN for the last field
        travel_distances.append(np.nan)
        travel_times.append(np.nan)
    else:
        travel_distances.append(np.nan)
        travel_times.append(np.nan)

    # Ensure lengths match for DataFrame
    if len(travel_distances) != len(field_areas_gunthas):
        travel_distances = travel_distances[:len(field_areas_gunthas)]
        travel_times = travel_times[:len(field_areas_gunthas)]

    # Combine area, time, dates, and travel metrics into a single DataFrame
    combined_df = pd.DataFrame({
        'Field ID': field_areas_gunthas.index,
        'Area (Gunthas)': field_areas_gunthas.values,
        'Time (Minutes)': field_times.values,
        'Start Date': field_dates['start_date'].values,
        'End Date': field_dates['end_date'].values,
        'Travel Distance to Next Field (km)': travel_distances,
        'Travel Time to Next Field (minutes)': travel_times
    })
    
    # Calculate total metrics
    total_area = field_areas_gunthas.sum()
    total_time = field_times.sum()
    total_travel_distance = np.nansum(travel_distances)
    total_travel_time = np.nansum(travel_times)

    # Create a satellite map
    map_center = [gps_data['lat'].mean(), gps_data['lng'].mean()]
    m = folium.Map(location=map_center, zoom_start=12)
    
    # Add Mapbox satellite imagery
    mapbox_token = 'pk.eyJ1IjoiZmxhc2hvcDAwNyIsImEiOiJjbHo5NzkycmIwN2RxMmtzZHZvNWpjYmQ2In0.A_FZYl5zKjwSZpJuP_MHiA'
    folium.TileLayer(
        tiles='https://api.mapbox.com/styles/v1/mapbox/satellite-v9/tiles/256/{z}/{x}/{y}?access_token=' + mapbox_token,
        attr='Mapbox Satellite Imagery',
        name='Satellite',
        overlay=True,
        control=True
    ).add_to(m)
    
    # Add fullscreen control
    plugins.Fullscreen(position='topright').add_to(m)

    # Plot the points on the map
    for idx, row in gps_data.iterrows():
        if row['field_id'] in valid_fields:
            color = 'blue'  # Blue for valid field points
        else:
            color = 'red'   # Red for travel points (noise)
        folium.CircleMarker(
            location=(row['lat'], row['lng']),
            radius=2,
            color=color,
            fill=True,
            fill_color=color
        ).add_to(m)

    # Conditionally display hull points if the checkbox is selected
    if show_hull_points:
        for field_id in valid_fields:
            field_points = fields[fields['field_id'] == field_id][['lat', 'lng']].values
            hull = ConvexHull(field_points)
            hull_points = field_points[hull.vertices]
            
            st.write(f"**Field ID {field_id} Hull Points:**")
            for point in hull_points:
                st.write(f"Lat: {point[0]}, Lng: {point[1]}")
            
            folium.Polygon(
                locations=hull_points.tolist(),
                color='green',
                fill=True,
                fill_color='green',
                fill_opacity=0.5
            ).add_to(m)
            
            additional_points = generate_more_hull_points(hull_points)
            folium.PolyLine(
                locations=additional_points.tolist(),
                color='yellow',
                weight=2,
                opacity=0.8
            ).add_to(m)

    return m, combined_df, total_area, total_time, total_travel_distance, total_travel_time

# Function to get the latest location from data
def get_latest_location(data):
    if not data:
        return None
    latest_data = data[-1]
    latest_location = (latest_data['lat'], latest_data['lon'])
    timestamp = pd.to_datetime(latest_data['time'], unit='ms')
    return latest_location, timestamp

# Function to create a map for the latest location
def create_latest_location_map(latest_location):
    m = folium.Map(location=latest_location, zoom_start=15)
    folium.Marker(
        location=latest_location,
        popup="Latest Location",
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(m)
    return m

# Streamlit app
def main():
    st.set_page_config(page_title="Field and Location Data Visualization", layout="wide")
    st.title("Field and Location Data Visualization")
    
    # Create tabs
    tabs = st.tabs(["Field Data Visualization", "Latest Location"])
    
    with tabs[0]:
        st.header("Field Data Visualization")
        
        # Input for vehicle ID and date range
        vehicle = st.text_input("Enter Vehicle ID:")
        start_date = st.date_input("Start Date", datetime.today() - timedelta(days=7))
        end_date = st.date_input("End Date", datetime.today())
        
        # Toggle switch for showing or hiding hull points
        show_hull_points = st.checkbox("Show Hull Points", value=True)
        
        if st.button("Fetch Data and Process"):
            if not vehicle:
                st.error("Please enter a Vehicle ID.")
            elif start_date > end_date:
                st.error("Start Date must be before End Date.")
            else:
                # Convert start_date and end_date to datetime.datetime objects in milliseconds
                start_time = int(datetime.combine(start_date, datetime.min.time()).timestamp() * 1000)
                end_time = int(datetime.combine(end_date, datetime.min.time()).timestamp() * 1000)

                with st.spinner("Fetching data..."):
                    data = fetch_data(vehicle, start_time, end_time)

                if data:
                    with st.spinner("Processing data..."):
                        map_obj, field_df, total_area, total_time, total_travel_distance, total_travel_time = process_data(data, show_hull_points)
                    
                    # Display the map
                    st.subheader("Field Map")
                    folium_static(map_obj, width=700, height=500)

                    # Display the DataFrame and totals
                    st.subheader("Field Metrics")
                    st.dataframe(field_df.style.format({
                        'Area (Gunthas)': "{:.2f}",
                        'Time (Minutes)': "{:.2f}",
                        'Travel Distance to Next Field (km)': "{:.2f}",
                        'Travel Time to Next Field (minutes)': "{:.2f}"
                    }))

                    st.markdown(f"**Total Area (Gunthas):** {total_area:.2f}")
                    st.markdown(f"**Total Time (Minutes):** {total_time:.2f}")
                    st.markdown(f"**Total Travel Distance (km):** {total_travel_distance:.2f}")
                    st.markdown(f"**Total Travel Time (minutes):** {total_travel_time:.2f}")
                    
                    # Add a download button for the map
                    map_filename = f"{vehicle}_map_{start_date.strftime('%Y%m%d')}_to_{end_date.strftime('%Y%m%d')}.html"
                    map_obj.save(map_filename)
                    with open(map_filename, "rb") as file:
                        btn = st.download_button(
                            label="Download Map as HTML",
                            data=file,
                            file_name=map_filename,
                            mime="text/html"
                        )
                    
                    # Clean up the file after download
                    if btn:
                        os.remove(map_filename)
    
    with tabs[1]:
        st.header("Latest Location")
        
        # Input for vehicle ID and date range
        vehicle_latest = st.text_input("Enter Vehicle ID for Latest Location:", key="latest")
        latest_start_date = st.date_input("Start Date", datetime.today() - timedelta(days=1), key="latest_start")
        latest_end_date = st.date_input("End Date", datetime.today(), key="latest_end")
        
        if st.button("Fetch Latest Location and Navigate", key="latest_button"):
            if not vehicle_latest:
                st.error("Please enter a Vehicle ID.")
            elif latest_start_date > latest_end_date:
                st.error("Start Date must be before End Date.")
            else:
                # Convert start_date and end_date to datetime.datetime objects in milliseconds
                latest_start_time = int(datetime.combine(latest_start_date, datetime.min.time()).timestamp() * 1000)
                latest_end_time = int(datetime.combine(latest_end_date, datetime.min.time()).timestamp() * 1000)

                with st.spinner("Fetching latest location data..."):
                    latest_data = fetch_data(vehicle_latest, latest_start_time, latest_end_time)

                if latest_data:
                    latest_info = get_latest_location(latest_data)
                    if latest_info:
                        latest_location, latest_timestamp = latest_info
                        with st.spinner("Creating map..."):
                            latest_map = create_latest_location_map(latest_location)
                        
                        # Display the latest location map
                        st.subheader("Latest Location Map")
                        folium_static(latest_map, width=700, height=500)

                        st.markdown(f"**Latest Timestamp:** {latest_timestamp}")

                        # Input for origin address
                        st.subheader("Get Directions to Latest Location")
                        origin = st.text_input("Enter Origin Address (for directions):")

                        if origin:
                            # Generate Google Maps directions link
                            origin_encoded = requests.utils.quote(origin)
                            destination_encoded = f"{latest_location[0]},{latest_location[1]}"
                            google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin_encoded}&destination={destination_encoded}&travelmode=driving"

                            st.markdown(f"[Click here for directions on Google Maps]({google_maps_url})")
                    else:
                        st.error("No location data available.")
                else:
                    st.error("No data fetched for the given parameters.")

# Helper function to display Folium maps in Streamlit
def folium_static(m, width=700, height=500):
    from streamlit_folium import st_folium
    st_folium(m, width=width, height=height)

if __name__ == "__main__":
    main()

from geopy.distance import geodesic

def calculate_distance(user_location, shelter_location):
    """
    Calculate distance (miles) between user and shelter.

    :param user_location: (tuple) (latitude, longitude) of the user
    :param shelter_location: (tuple) (latitude, longitude) of the shelter
    :return: Distance in miles
    """
    return geodesic(user_location, shelter_location).miles

def filter_nearest_resources(user_lat, user_lon, resources, max_distance=50):
    """
    Filters resources within a given distance from the user.

    :param user_lat: (float) User's latitude
    :param user_lon: (float) User's longitude
    :param resources: (list) List of resource dictionaries
    :param max_distance: (int) Maximum distance (in miles)
    :return: List of nearby resources sorted by distance
    """
    user_location = (user_lat, user_lon)

    for resource in resources:
        resource_location = (resource["latitude"], resource["longitude"])
        resource["distance"] = calculate_distance(user_location, resource_location)

    # Filter resources within the given distance range
    nearby_resources = [r for r in resources if r["distance"] <= max_distance]

    # Sort by closest distance
    return sorted(nearby_resources, key=lambda x: x["distance"])


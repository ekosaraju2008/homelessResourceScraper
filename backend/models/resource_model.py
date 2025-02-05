from typing import Dict

class ResourceModel:
    """
    Defines the structure of resources stored in MongoDB.
    This includes shelters, food banks, and other aid resources.
    """

    def __init__(self, name: str, resource_type: str, address: str, latitude: float, longitude: float, eligibility: str, hours: str):
        self.name = name
        self.type = resource_type  # e.g., "shelter", "food_bank"
        self.address = address
        self.latitude = latitude
        self.longitude = longitude
        self.eligibility = eligibility
        self.hours = hours

    def to_dict(self) -> Dict:
        """
        Converts the ResourceModel object into a dictionary (MongoDB-friendly).
        """
        return {
            "name": self.name,
            "type": self.type,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "eligibility": self.eligibility,
            "hours": self.hours
        }

    @staticmethod
    def from_dict(data: Dict):
        """
        Converts a dictionary into a ResourceModel object.
        """
        return ResourceModel(
            name=data.get("name"),
            resource_type=data.get("type"),
            address=data.get("address"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            eligibility=data.get("eligibility"),
            hours=data.get("hours")
        )


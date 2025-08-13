from django.db import models

class Currency(models.TextChoices):
    CLP = 'CLP', 'Chilean Peso'
    USD = 'USD', 'US Dollar'
    EUR = 'EUR', 'Euro'
    GBP = 'GBP', 'British Pound'
    JPY = 'JPY', 'Japanese Yen'
    BRL = 'BRL', 'Brazilian Real'
    MXN = 'MXN', 'Mexican Peso'
    INR = 'INR', 'Indian Rupee'
    CNY = 'CNY', 'Chinese Yuan'
    CAD = 'CAD', 'Canadian Dollar'
    AUD = 'AUD', 'Australian Dollar'

class Language(models.TextChoices):
    ES = 'ES', 'Spanish'
    EN = 'EN', 'English'
    FR = 'FR', 'French'
    DE = 'DE', 'German'
    JA = 'JA', 'Japanese'
    PT = 'PT', 'Portuguese'
    ZH = 'ZH', 'Chinese'
    HI = 'HI', 'Hindi'

class Nationality(models.TextChoices):
    CL = 'CL', 'Chile'
    AR = 'AR', 'Argentina'
    US = 'US', 'United States'
    ES = 'ES', 'Spain'
    FR = 'FR', 'France'
    DE = 'DE', 'Germany'
    JP = 'JP', 'Japan'
    BR = 'BR', 'Brazil'
    MX = 'MX', 'Mexico'
    GB = 'GB', 'United Kingdom'
    IT = 'IT', 'Italy'
    CN = 'CN', 'China'
    IN = 'IN', 'India'
    CA = 'CA', 'Canada'
    AU = 'AU', 'Australia'

class Gender(models.TextChoices):
    MALE = 'M', 'Male'
    FEMALE = 'F', 'Female'
    OTHER = 'O', 'Other'
    UNSPECIFIED = 'U', 'Prefer not to say'

class OrganizationUserRole(models.TextChoices):
    ADMIN = 'ADMIN', 'Administrator'
    STAFF = 'STAFF', 'Staff'
    MANAGER = 'MANAGER', 'Manager'
    VIEWER = 'VIEWER', 'Viewer'

class InteractionAction(models.TextChoices):
    VIEW = 'VIEW', 'View'
    CLICK = 'CLICK', 'Click'
    BOOK = 'BOOK', 'Book'
    SHARE = 'SHARE', 'Share'
    LIKE = 'LIKE', 'Like'
    COMMENT = 'COMMENT', 'Comment',
    SEARCH = 'SEARCH', 'Search'

class SubscriptionPlan(models.TextChoices):
    FREE = 'FREE', 'Free'
    BASIC = 'BASIC', 'Basic'
    PRO = 'PRO', 'Pro'
    ENTERPRISE = 'ENTERPRISE', 'Enterprise'

class OrganizationCategory(models.TextChoices):
    EDUCATION = 'EDUCATION', 'Educación'
    HEALTHCARE = 'HEALTHCARE', 'Salud'
    NONPROFIT = 'NONPROFIT', 'ONG'
    GOVERNMENT = 'GOVERNMENT', 'Gobierno'
    PRIVATE = 'PRIVATE', 'Privada'
    OTHER = 'OTHER', 'Otro'

class ZoneLevel(models.TextChoices):
    COUNTRY = 'COUNTRY', 'País'
    REGION = 'REGION', 'Región'
    CITY = 'CITY', 'Ciudad'
    DISTRICT = 'DISTRICT', 'Comuna'
    NEIGHBORHOOD = 'NEIGHBORHOOD', 'Barrio'

class PlaceType(models.TextChoices):
    PARK = 'park', 'Park'
    RESTAURANT = 'restaurant', 'Restaurant'
    CAFE = 'cafe', 'Café'
    SCHOOL = 'school', 'School'
    HOSPITAL = 'hospital', 'Hospital'
    HOTEL = 'hotel', 'Hotel'
    MUSEUM = 'museum', 'Museum'
    SUPERMARKET = 'supermarket', 'Supermarket'
    BUS_STOP = 'bus_stop', 'Bus Stop'
    TRAIN_STATION = 'train_station', 'Train Station'
    BEACH = 'beach', 'Beach'
    VIEWPOINT = 'viewpoint', 'Viewpoint'
    CLIMBING_GYM = 'climbing_gym', 'Climbing Gym'
    CAMPGROUND = 'campground', 'Campground'
    PARKING = 'parking', 'Parking'

class ReservationStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pendiente'
    CONFIRMED = 'CONFIRMED', 'Confirmada'
    CANCELLED = 'CANCELLED', 'Cancelada'
    EXPIRED = 'EXPIRED', 'Expirada'
    COMPLETED = 'COMPLETED', 'Completada'
    REJECTED = 'REJECTED', 'Rechazada'
    REFUNDED = 'REFUNDED', 'Reembolsada'
    WAITLISTED = 'WAITLISTED', 'En lista de espera'
    UNDER_REVIEW = 'UNDER_REVIEW', 'En revisión'

class UserRole(models.TextChoices):
    OWNER = 'OWNER', 'Creador' 
    EDITOR = 'EDITOR', 'Editor'
    VIEWER = 'VIEWER', 'Visualizador'

class ImagePosition(models.TextChoices):
    COVER = 'COVER', 'Portada'
    GALLERY = 'GALLERY', 'Galería'
    ICON = 'ICON', 'Ícono'
    BACKGROUND = 'BACKGROUND', 'Fondo'
    MAP_MARKER = 'MAP_MARKER', 'Marcador de mapa'
    AVATAR = 'AVATAR', 'Avatar'
    DETAIL = 'DETAIL', 'Detalle'

class TransportType(models.TextChoices):
    BUS = 'BUS', 'Bus'
    TRAIN = 'TRAIN', 'Tren'
    CAR = 'CAR', 'Auto'
    BIKE = 'BIKE', 'Bicicleta'
    PLANE = 'PLANE', 'Avión'
    BOAT = 'BOAT', 'Barco'

class AccommodationType(models.TextChoices):
    HOTEL = 'HOTEL', 'Hotel'
    HOSTEL = 'HOSTEL', 'Hostal'
    AIRBNB = 'AIRBNB', 'Airbnb'
    CAMPING = 'CAMPING', 'Camping'
    GUESTHOUSE = 'GUESTHOUSE', 'Casa de huéspedes'

class ActivityType(models.TextChoices):
    HIKING = 'HIKING', 'Senderismo'
    MUSEUM = 'MUSEUM', 'Museo'
    BEACH = 'BEACH', 'Playa'
    SKIING = 'SKIING', 'Esquí'
    SHOPPING = 'SHOPPING', 'Compras'
    CLIMBING = 'CLIMBING', 'Escalada'
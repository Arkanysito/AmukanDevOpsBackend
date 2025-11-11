# apps/experiences/management/commands/load_viña_data.py
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.organizations.models import Organization
from apps.location.models import Place, Zone
from apps.experiences.models import ActivityService, Event
from apps.core.constants import (
    ActivityType, Currency, PlaceType
)


class Command(BaseCommand):
    help = 'Carga completa de todos los lugares, actividades y eventos de Viña del Mar y Valparaíso'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Iniciando carga completa de datos de Viña del Mar...')
        )
        
        try:
            with transaction.atomic():
                self.get_organizations_and_zones()
                self.get_existing_places()
                self.create_all_activities() 
                self.create_all_events()
                
            self.stdout.write(
                self.style.SUCCESS('¡Carga completa finalizada exitosamente!')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error durante la carga: {str(e)}')
            )
            raise

    def get_organizations_and_zones(self):
        """Obtiene las organizaciones y zonas existentes"""
        self.stdout.write('Obteniendo organizaciones y zonas...')
        
        try:
            self.org_municipal = Organization.objects.get(name="Municipalidad de Viña del Mar")
            self.stdout.write(f'  ✓ Organización obtenida: {self.org_municipal.name}')
        except Organization.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ Organización "Municipalidad de Viña del Mar" no encontrada')
            )
            raise
        
        try:
            self.org_usm = Organization.objects.get(name="Universidad Técnica Federico Santa María")
            self.stdout.write(f'  ✓ Organización obtenida: {self.org_usm.name}')
        except Organization.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ Organización "Universidad Técnica Federico Santa María" no encontrada')
            )
            raise
        
        try:
            self.org_duoc = Organization.objects.get(name="DUOC UC")
            self.stdout.write(f'  ✓ Organización obtenida: {self.org_duoc.name}')
        except Organization.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ Organización "DUOC UC" no encontrada')
            )
            raise
        
        try:
            self.zone_viña = Zone.objects.get(name="Viña Del Mar")
            self.stdout.write(f'  ✓ Zona obtenida: {self.zone_viña.name}')
        except Zone.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ Zona "Viña del Mar" no encontrada')
            )
            raise
        
        try:
            self.zone_valpo = Zone.objects.get(name="Valparaíso")
            self.stdout.write(f'  ✓ Zona obtenida: {self.zone_valpo.name}')
        except Zone.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('  ✗ Zona "Valparaíso" no encontrada')
            )
            raise

    def get_existing_places(self):
        """Obtiene los lugares existentes de la base de datos"""
        self.stdout.write('Obteniendo lugares existentes...')
        
        # Buscar lugares por nombres aproximados
        place_names = [
            "Parque Quinta Vergara",
            "Sala Viña del Mar", 
            "Reloj de Flores",
            "Castillo Wulff",
            "Casino de Viña del Mar",
            "Muelle Vergara",
            "Parque San Martín",
            "Borde Costero Viña del Mar",
            "Parque Sausalito",
            "Valparaíso Sporting Club",
            "Parroquia Santa María de los Ángeles San Expedito",
            "Teatro Municipal Viña del Mar",
            "UTFSM Sede José Miguel Carrera",
            "Casa Yungay",
            "Trotamundos Valparaíso",
            "Centro Cultural Alonso de Ercilla"
        ]
        
        self.places = {}
        
        for name in place_names:
            try:
                # Buscar por nombre que contenga el texto (case insensitive)
                place = Place.objects.filter(name__icontains=name).first()
                if place:
                    self.places[name] = place
                    self.stdout.write(f'  ✓ Lugar encontrado: {place.name}')
                else:
                    self.stdout.write(f'  ⚠ Lugar no encontrado: {name}')
            except Exception as e:
                self.stdout.write(f'  ⚠ Error buscando lugar {name}: {str(e)}')
        
        # Asignar lugares específicos para uso en eventos
        self.teatro_municipal = self.places.get("Teatro Municipal Viña del Mar")
        self.utfsm_carrera = self.places.get("UTFSM Sede José Miguel Carrera")
        self.casa_yungay = self.places.get("Casa Yungay")
        self.trotamundos_valpo = self.places.get("Trotamundos Valparaíso")
        self.lugar_conferencia = self.places.get("Centro Cultural Alonso de Ercilla")
        self.sala_viña = self.places.get("Sala Viña del Mar")

        # Verificar que tenemos los lugares necesarios para eventos
        required_places = {
            "Teatro Municipal Viña del Mar": self.teatro_municipal,
            "UTFSM Sede José Miguel Carrera": self.utfsm_carrera,
            "Sala Viña del Mar": self.sala_viña
        }
        
        for name, place in required_places.items():
            if not place:
                self.stdout.write(
                    self.style.WARNING(f'  ⚠ Lugar requerido no encontrado: {name}')
                )

    def create_all_activities(self):
        """Crea todas las actividades"""
        self.stdout.write('Creando actividades...')

        # Obtener el lugar para Palacio Vergara si existe
        palacio_vergara_place = self.places.get("Parque Quinta Vergara")

        # 1. PALACIO VERGARA
        palacio_vergara, created = ActivityService.objects.update_or_create(
            name="Recorrido Palacio Vergara",
            defaults={
                'organization_id': self.org_municipal,
                'place_id': palacio_vergara_place,
                'description': "Visita guiada por el majestuoso Palacio Vergara, emblemático edificio de estilo europeo que alberga el museo de bellas artes",
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'activity_type': ActivityType.MUSEUM,
                'duration_minutes': 90,
                'guide_included': True,
                'details': {
                    'horario': "Martes a domingo 10:00 a 17:30 hrs (horario continuo)",
                    'inscripcion': "Inscripción previa en recepción",
                    'redes_sociales': "@museopalaciovergara"
                },
                'capacity': 25,
                'rating': Decimal('4.6')
            }
        )
        if created:
            self.stdout.write(f'  ✓ Actividad creada: {palacio_vergara.name}')

        # 2. MUSEO ARTEQUIN
        museo_artequin, created = ActivityService.objects.update_or_create(
            name="Museo Artequin Viña del Mar",
            defaults={
                'organization_id': self.org_municipal,
                'description': "Museo interactivo de arte que busca acercar el arte a niños y jóvenes mediante reproducciones de obras famosas y actividades educativas",
                'price': Decimal('2300'),
                'price_currency': Currency.CLP,
                'activity_type': ActivityType.MUSEUM,
                'duration_minutes': 120,
                'guide_included': True,
                'details': {
                    'horario': "Lunes a viernes 09:30 a 13:00 hrs. / 14:00 a 18:00 hrs. Sábados y domingos 10:00 a 14:00 - 15:00 a 18:00 hrs",
                    'precios_especiales': "Estudiantes, Niños y tercera edad: $1.500",
                    'sitio_web': "https://artequinvina.cl/"
                },
                'capacity': 40,
                'rating': Decimal('4.4')
            }
        )
        if created:
            self.stdout.write(f'  ✓ Actividad creada: {museo_artequin.name}')

        # 3. MUSEO PALACIO RIOJA
        museo_rioja, created = ActivityService.objects.update_or_create(
            name="Museo Palacio Rioja",
            defaults={
                'organization_id': self.org_municipal,
                'description': "Importante monumento nacional que muestra la arquitectura y estilo de vida de la aristocracia viñamarina de principios del siglo XX",
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'activity_type': ActivityType.MUSEUM,
                'duration_minutes': 75,
                'guide_included': True,
                'details': {
                    'horario': "Martes a domingo 10:00 a 17:30 hrs (horario continuo)",
                    'redes_sociales': "@museopalaciorioja"
                },
                'capacity': 30,
                'rating': Decimal('4.5')
            }
        )
        if created:
            self.stdout.write(f'  ✓ Actividad creada: {museo_rioja.name}')

        # 4. RESIDENCIA PALACIO PRESIDENCIAL
        residencia_presidencial, created = ActivityService.objects.update_or_create(
            name="Visita Residencia Palacio Presidencial",
            defaults={
                'organization_id': self.org_municipal,
                'description': "Visita guiada a la residencia presidencial de Cerro Castillo, con impresionantes vistas al mar y arquitectura única",
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'activity_type': ActivityType.WALKING_TOUR,
                'duration_minutes': 60,
                'guide_included': True,
                'details': {
                    'inscripcion': "Solo con inscripción previa en https://visitasguiadascerrocastillo.presidencia.cl/",
                    'ubicacion': "Callao 398, Cerro Castillo"
                },
                'capacity': 20,
                'rating': Decimal('4.8')
            }
        )
        if created:
            self.stdout.write(f'  ✓ Actividad creada: {residencia_presidencial.name}')

        # 5. MUSEO FONCK
        museo_fonck, created = ActivityService.objects.update_or_create(
            name="Museo de Arqueología e Historia Francisco Fonck",
            defaults={
                'organization_id': self.org_municipal,
                'description': "Importante museo que alberga una valiosa colección de arqueología y historia natural, incluyendo moáis de Isla de Pascua",
                'price': Decimal('4500'),
                'price_currency': Currency.CLP,
                'activity_type': ActivityType.MUSEUM,
                'duration_minutes': 90,
                'guide_included': False,
                'details': {
                    'horario': "Lunes 10:00 a 14:00 - 15:00 a 18:00 / martes a sábado 10:00 a 18:00 hrs. Domingo y festivos 10:00 a 14:00 hrs",
                    'precios_especiales': "Niños/Estudiantes: $1.000",
                    'sitio_web': "www.museofonck.cl"
                },
                'capacity': 50,
                'rating': Decimal('4.4')
            }
        )
        if created:
            self.stdout.write(f'  ✓ Actividad creada: {museo_fonck.name}')

        # 6. JARDÍN BOTÁNICO
        jardin_botanico, created = ActivityService.objects.update_or_create(
            name="Jardín Botánico Nacional",
            defaults={
                'organization_id': self.org_municipal,
                'description': "Extenso jardín botánico con más de 3,000 especies de plantas, senderos educativos y hermosos paisajes naturales",
                'price': Decimal('3000'),
                'price_currency': Currency.CLP,
                'activity_type': ActivityType.HIKING,
                'duration_minutes': 180,
                'guide_included': False,
                'details': {
                    'horario': "Lunes a domingo y festivos 09:00 a 17:30 / cierre 18:00 hrs",
                    'precios_especiales': "Adultos mayores, niños y estudiantes: $1.500 / Niños 0-4 años: Gratis",
                    'estacionamiento': "Autos $3.000 / Motos $1.500",
                    'sitio_web': "https://jbn.cl/wp/"
                },
                'capacity': 100,
                'rating': Decimal('4.6')
            }
        )
        if created:
            self.stdout.write(f'  ✓ Actividad creada: {jardin_botanico.name}')

    def create_all_events(self):
        """Crea todos los eventos"""
        self.stdout.write('Creando eventos...')

        # Verificar que tenemos los lugares necesarios
        if not self.teatro_municipal:
            self.stdout.write(
                self.style.ERROR('  ✗ No se puede crear eventos: Teatro Municipal no encontrado')
            )
            return

        if not self.utfsm_carrera:
            self.stdout.write(
                self.style.WARNING('  ⚠ UTFSM no encontrada, algunos eventos no se crearán')
            )

        # 1. Feria De Software (solo si tenemos el lugar)
        if self.utfsm_carrera:
            feria_software, created = Event.objects.update_or_create(
                name="Feria De Software USM",
                start_date=datetime(2025, 11, 13, 10, 0),
                defaults={
                    'organization_id': self.org_usm,
                    'place_id': self.utfsm_carrera,
                    'description': "Feria de software USM viña del mar",
                    'end_date': datetime(2025, 11, 13, 18, 0),
                    'price': Decimal('0'),
                    'price_currency': Currency.CLP,
                    'is_featured': True,
                    'rating': Decimal('5.0'),
                    'capacity': 200,
                    'details': {
                        'tipo': "Feria tecnológica",
                        'universidad': "Universidad Técnica Federico Santa María"
                    }
                }
            )
            if created:
                self.stdout.write(f'  ✓ Evento creado: {feria_software.name}')

        # 2. Cine Club DUOC UC
        cine_club, created = Event.objects.update_or_create(
            name="Cine Club DUOC UC: Pequeña Miss Sunshine",
            start_date=datetime(2025, 11, 12, 19, 0),
            defaults={
                'organization_id': self.org_duoc,
                'place_id': self.teatro_municipal,
                'description': "Proyección y conversatorio con Gonzalo Frías sobre cine independiente y narrativas familiares",
                'end_date': datetime(2025, 11, 12, 22, 0),
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'rating': Decimal('4.8'),
                'capacity': 150,
                'details': {
                    'actividad': "Cine y conversatorio",
                    'instrucciones': "Entrada liberada, cupos limitados, actividad cultural",
                    'pelicula': "Pequeña Miss Sunshine"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {cine_club.name}')

        # 3. GOD SAVE THE QUEEN - WORLD TOUR 2025
        queen_tribute, created = Event.objects.update_or_create(
            name="GOD SAVE THE QUEEN - WORLD TOUR 2025 HOMENAJE A QUEEN",
            start_date=datetime(2025, 11, 13, 21, 0),
            defaults={
                'organization_id': self.org_municipal,
                'place_id': self.teatro_municipal,
                'description': "Banda argentina liderada por Pablo Padín presenta un espectacular homenaje a Queen",
                'end_date': datetime(2025, 11, 13, 23, 30),
                'price': Decimal('75000'),
                'price_currency': Currency.CLP,
                'is_featured': True,
                'rating': Decimal('5.0'),
                'capacity': 800,
                'details': {
                    'venta_entradas': "www.ticketplus.cl",
                    'banda': "God Save The Queen",
                    'genero': "Tributo a Queen"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {queen_tribute.name}')

        # 4. 10 AÑOS FESTIVAL UDARA
        festival_udara, created = Event.objects.update_or_create(
            name="10 AÑOS FESTIVAL UDARA CULTURA, MUJERES Y ROCK",
            start_date=datetime(2025, 11, 14, 20, 0),
            defaults={
                'organization_id': self.org_municipal,
                'place_id': self.teatro_municipal,
                'description': "Celebración de 10 años del Festival Udara con participación de Camila Moreno, América Paz, Banda UDARA, Cactus Andante",
                'end_date': datetime(2025, 11, 14, 23, 0),
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'is_featured': True,
                'rating': Decimal('5.0'),
                'capacity': 600,
                'details': {
                    'artistas': ["Camila Moreno", "América Paz", "Banda UDARA", "Cactus Andante"],
                    'instrucciones': "Actividad gratuita con inscripción previa",
                    'genero': "Rock, Música chilena"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {festival_udara.name}')

        # 5. CONCIERTO ORQUESTA SINFÓNICA JUVENIL
        orquesta_juvenil, created = Event.objects.update_or_create(
            name="CONCIERTO ORQUESTA SINFÓNICA JUVENIL DE VALPARAÍSO",
            start_date=datetime(2025, 11, 15, 19, 30),
            defaults={
                'organization_id': self.org_municipal,
                'place_id': self.teatro_municipal,
                'description': "Concierto dirigido por Jesús Rodríguez con la Orquesta Sinfónica Juvenil de Valparaíso",
                'end_date': datetime(2025, 11, 15, 21, 30),
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'rating': Decimal('5.0'),
                'capacity': 700,
                'details': {
                    'director': "Jesús Rodríguez",
                    'orquesta': "Orquesta Sinfónica Juvenil de Valparaíso",
                    'instrucciones': "Actividad gratuita con inscripción previa"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {orquesta_juvenil.name}')

        # 6. PREMIOS DE LAS CULTURAS 2025
        premios_culturas, created = Event.objects.update_or_create(
            name="PREMIOS DE LAS CULTURAS, LAS ARTES Y EL PATRIMONIO 2025",
            start_date=datetime(2025, 11, 18, 19, 0),
            defaults={
                'organization_id': self.org_municipal,
                'place_id': self.teatro_municipal,
                'description': "Ceremonia de premiación con participación de Kennya Comesaña, Carlos Cabezas, Denisse Malebrán, Andrés de León y Puerto Orquesta Big Band",
                'end_date': datetime(2025, 11, 18, 22, 0),
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'is_featured': True,
                'rating': Decimal('5.0'),
                'capacity': 500,
                'details': {
                    'artistas': ["Kennya Comesaña", "Carlos Cabezas", "Denisse Malebrán", "Andrés de León", "Puerto Orquesta Big Band"],
                    'tipo_evento': "Ceremonia de premiación",
                    'instrucciones': "Actividad gratuita con inscripción previa"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {premios_culturas.name}')

        # 7. DANZA "100 AÑOS LUZ DE SOLEDAD"
        danza_butoh, created = Event.objects.update_or_create(
            name='PRESENTACIÓN DE DANZA "100 AÑOS LUZ DE SOLEDAD"',
            start_date=datetime(2025, 11, 19, 20, 0),
            defaults={
                'organization_id': self.org_municipal,
                'place_id': self.teatro_municipal,
                'description': "Actividad en el marco del festival internacional de Butoh en Chile",
                'end_date': datetime(2025, 11, 19, 21, 30),
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'rating': Decimal('5.0'),
                'capacity': 300,
                'details': {
                    'disciplina': "Danza Butoh",
                    'festival': "Festival Internacional de Butoh en Chile",
                    'instrucciones': "Actividad gratuita con inscripción previa"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {danza_butoh.name}')

        # 8. FULL: LA MÚSICA DE FULANO
        musica_fulano, created = Event.objects.update_or_create(
            name="FULL: LA MÚSICA DE FULANO",
            start_date=datetime(2025, 11, 21, 21, 0),
            defaults={
                'organization_id': self.org_municipal,
                'place_id': self.teatro_municipal,
                'description': "Homenaje a Fulano con participación de Jorge Campos, Willy Valenzuela, Paquita Rivera, Cuti Aste, Andrés Pérez, Cristobal Dahm y Guillermo Atria",
                'end_date': datetime(2025, 11, 21, 23, 0),
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'rating': Decimal('5.0'),
                'capacity': 600,
                'details': {
                    'artistas': ["Jorge Campos", "Willy Valenzuela", "Paquita Rivera", "Cuti Aste", "Andrés Pérez", "Cristobal Dahm", "Guillermo Atria"],
                    'tributo': "Fulano",
                    'genero': "Jazz fusión, Rock progresivo",
                    'instrucciones': "Actividad gratuita con inscripción previa"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {musica_fulano.name}')

        # 9. FICVIÑA 2025 - Festival de Cine
        ficviña, created = Event.objects.update_or_create(
            name="FICVIÑA 2025 - 37° Festival Internacional de Cine",
            start_date=datetime(2025, 11, 24, 10, 0),
            defaults={
                'organization_id': self.org_municipal,
                'place_id': self.teatro_municipal,
                'description': "37° Festival Internacional de Cine de Viña del Mar",
                'end_date': datetime(2025, 11, 29, 22, 0),
                'price': Decimal('0'),
                'price_currency': Currency.CLP,
                'is_featured': True,
                'rating': Decimal('5.0'),
                'capacity': 1000,
                'details': {
                    'tipo': "Festival de Cine Internacional",
                    'duracion': "6 días",
                    'edicion': "37°",
                    'instrucciones': "Actividad gratuita con inscripción previa"
                }
            }
        )
        if created:
            self.stdout.write(f'  ✓ Evento creado: {ficviña.name}')

        # 10. ART & WINE - Edición flúor (solo si tenemos el lugar)
        if self.casa_yungay:
            art_wine, created = Event.objects.update_or_create(
                name="ART & WINE - Edición flúor",
                start_date=datetime(2025, 11, 29, 17, 0),
                defaults={
                    'organization_id': self.org_municipal,
                    'place_id': self.casa_yungay,
                    'description': "¡Experiencia única en la oscuridad! Durante dos horas, tendrás la oportunidad de pintar tu propio cuadro con pintura fluorescente en la oscuridad, mientras disfrutas de vino ilimitado.",
                    'end_date': datetime(2025, 11, 29, 22, 0),
                    'price': Decimal('11000'),
                    'price_currency': Currency.CLP,
                    'rating': Decimal('4.0'),
                    'capacity': 50,
                    'details': {
                        'incluye': [
                            "Vino con recargas ilimitadas",
                            "Todos los materiales necesarios",
                            "Clase impartida por especialista en arte",
                            "Obra terminada para llevar a casa"
                        ],
                        'horarios': "Entradas para las 17 y 20 horas",
                        'precio_rango': "11000-16500 CLP",
                        'enlaces': [
                            "https://ticketplus.cl/events/art-wine-edicion-fluor",
                            "https://ticketplus.cl/events/art-wine-edicion-fluor-29-noviembre-20-horas"
                        ],
                        'requisitos': "No se necesitan conocimientos previos de pintura"
                    }
                }
            )
            if created:
                self.stdout.write(f'  ✓ Evento creado: {art_wine.name}')

        # 11. Concierto "Catalina y Las Bordonas de Oro" (solo si tenemos el lugar)
        if self.trotamundos_valpo:
            catalina_bordonas, created = Event.objects.update_or_create(
                name='Concierto "Catalina y Las Bordonas de Oro"',
                start_date=datetime(2025, 11, 14, 21, 0),
                defaults={
                    'organization_id': self.org_municipal,
                    'place_id': self.trotamundos_valpo,
                    'description': "Catalina y las Bordonas de Oro vuelven a Valparaíso para ofrecer una velada llena de emoción y romanticismo. Con un repertorio que rescata los boleros de antaño.",
                    'end_date': datetime(2025, 11, 14, 23, 0),
                    'price': Decimal('10000'),
                    'price_currency': Currency.CLP,
                    'rating': Decimal('5.0'),
                    'capacity': 100,
                    'details': {
                        'estilo': "Boleros, música romántica",
                        'banda': "Catalina y Las Bordonas de Oro",
                        'asientos': "Por orden de llegada, capacidad limitada",
                        'ambiente': "Noche íntima y nostálgica"
                    }
                }
            )
            if created:
                self.stdout.write(f'  ✓ Evento creado: {catalina_bordonas.name}')

        # 12. Conferencia "Sólo una Trampa Pudo Vencerlos" (solo si tenemos el lugar)
        if self.lugar_conferencia:
            conferencia_bomberos, created = Event.objects.update_or_create(
                name='Conferencia "Sólo una Trampa Pudo Vencerlos"',
                start_date=datetime(2025, 11, 20, 19, 0),
                defaults={
                    'organization_id': self.org_municipal,
                    'place_id': self.lugar_conferencia,
                    'description': "Conferencia sobre la tragedia ocurrida en 1953 cuando muchos bomberos perdieron la vida tratando de extinguir un incendio en Valparaíso",
                    'end_date': datetime(2025, 11, 20, 21, 0),
                    'price': Decimal('0'),
                    'price_currency': Currency.CLP,
                    'rating': Decimal('4.8'),
                    'capacity': 80,
                    'details': {
                        'tema': "Historia de bomberos de Valparaíso",
                        'duracion': "2 horas",
                        'modalidad': "Presencial",
                        'año_historico': "1953"
                    }
                }
            )
            if created:
                self.stdout.write(f'  ✓ Evento creado: {conferencia_bomberos.name}')

        # 13. El Tarot y sus imágenes musicales (solo si tenemos el lugar)
        if self.sala_viña:
            evento_tarot, created = Event.objects.update_or_create(
                name="El Tarot y sus imágenes musicales. Abrazo a nuestros padres",
                start_date=datetime(2015, 11, 21, 19, 0),
                defaults={
                    'organization_id': self.org_municipal,
                    'place_id': self.sala_viña,
                    'description': "El libro sagrado del tarot, relata mediante símbolos el desarrollo espiritual del ser humano, la transformación de su energía vital en conciencia y su definitiva iluminación",
                    'end_date': datetime(2015, 11, 21, 21, 0),
                    'price': Decimal('0'),
                    'price_currency': Currency.CLP,
                    'rating': Decimal('4.0'),
                    'capacity': 60,
                    'details': {
                        'tema': "Tarot y desarrollo espiritual",
                        'duracion': "2 horas",
                        'modalidad': "Presencial",
                        'enfoque': "Imágenes musicales y simbolismo"
                    }
                }
            )
            if created:
                self.stdout.write(f'  ✓ Evento creado: {evento_tarot.name}')

        self.stdout.write(f'  ✓ Total de eventos creados/actualizados: {Event.objects.count()}')

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Eliminar datos existentes antes de cargar',
        )
class ItineraryValidator:
    """Valida la calidad y viabilidad de los itinerarios generados"""
    
    @staticmethod
    def validate_itinerary(itinerary, budget, days):
        """Valida un itinerario y retorna score de calidad"""
        validation_results = {
            'is_valid': True,
            'issues': [],
            'quality_score': 0,
            'metrics': {}
        }
        
        items = itinerary.get('items', [])
        total_cost = itinerary.get('total_cost', 0)
        
        # 1. Validar presupuesto
        if total_cost > budget:
            validation_results['is_valid'] = False
            validation_results['issues'].append('Budget exceeded')
        
        budget_usage = total_cost / budget if budget > 0 else 0
        validation_results['metrics']['budget_usage'] = budget_usage
        
        # 2. Validar distribución temporal
        activities_by_day = {}
        avg_activities = 0
        for item in items:
            if item['type'] in ['activity', 'event']:
                day = item['date'].date()
                activities_by_day[day] = activities_by_day.get(day, 0) + 1
        
        if activities_by_day:
            avg_activities = sum(activities_by_day.values()) / len(activities_by_day)
            validation_results['metrics']['avg_activities_per_day'] = avg_activities
            
            # Penalizar días vacíos o sobrecargados
            if avg_activities < 2:
                validation_results['issues'].append('Too few activities per day')
            elif avg_activities > 6:
                validation_results['issues'].append('Too many activities per day')
        
        # 3. Validar diversidad
        activity_types = [item['service'].__class__.__name__ for item in items if item.get('service')]
        diversity_score = len(set(activity_types)) / len(activity_types) if activity_types else 0
        validation_results['metrics']['diversity'] = diversity_score
        
        # 4. Calcular score de calidad (0-100)
        quality_score = 0
        
        # Budget efficiency (30 puntos)
        if 0.7 <= budget_usage <= 0.95:
            quality_score += 30
        elif 0.5 <= budget_usage < 0.7:
            quality_score += 20
        elif budget_usage > 0.95:
            quality_score += 25
        
        # Activities distribution (30 puntos)
        if 2 <= avg_activities <= 5:
            quality_score += 30
        elif 1 <= avg_activities < 2 or 5 < avg_activities <= 6:
            quality_score += 20
        
        # Diversity (20 puntos)
        quality_score += diversity_score * 20
        
        # Completeness (20 puntos)
        has_accommodation = any(item['type'] == 'accommodation' for item in items)
        has_dining = any(item['type'] == 'dining' for item in items)
        has_activities = any(item['type'] == 'activity' for item in items)
        
        completeness = sum([has_accommodation or days == 1, has_dining, has_activities])
        quality_score += (completeness / 3) * 20
        
        validation_results['quality_score'] = round(quality_score, 2)
        
        return validation_results


# Sistema de comparación de itinerarios
class ItineraryComparator:
    """Compara múltiples itinerarios y sugiere el mejor según criterios"""
    
    @staticmethod
    def compare_itineraries(itineraries, user_priorities=None):
        """
        Compara itinerarios y retorna ranking
        
        Args:
            itineraries: Lista de itinerarios
            user_priorities: Dict con pesos para criterios
                {'budget': 0.3, 'activities': 0.4, 'diversity': 0.3}
        """
        if not itineraries:
            return []
        
        # Prioridades por defecto
        priorities = user_priorities or {
            'budget_efficiency': 0.35,
            'activity_count': 0.25,
            'diversity': 0.20,
            'quality': 0.20
        }
        
        comparisons = []
        
        for idx, itinerary in enumerate(itineraries):
            items = itinerary.get('items', [])
            
            # Métricas
            activity_count = sum(1 for item in items if item['type'] in ['activity', 'event'])
            
            activity_types = [
                item['service'].__class__.__name__ 
                for item in items 
                if item.get('service')
            ]
            diversity = len(set(activity_types)) / len(activity_types) if activity_types else 0
            
            budget_util = itinerary.get('budget_utilization', 0)
            
            # Score compuesto
            score = (
                priorities['budget_efficiency'] * budget_util * 100 +
                priorities['activity_count'] * min(activity_count / 5, 1) * 100 +
                priorities['diversity'] * diversity * 100 +
                priorities['quality'] * 80  # Base quality score
            )
            
            comparisons.append({
                'index': idx,
                'strategy': itinerary.get('strategy', 'unknown'),
                'score': score,
                'metrics': {
                    'activity_count': activity_count,
                    'diversity': round(diversity, 2),
                    'budget_utilization': round(budget_util, 2),
                    'total_cost': itinerary.get('total_cost', 0)
                },
                'recommendation': ItineraryComparator._get_recommendation(
                    itinerary.get('strategy'), score
                )
            })
        
        # Ordenar por score
        comparisons.sort(key=lambda x: x['score'], reverse=True)
        
        return comparisons
    
    @staticmethod
    def _get_recommendation(strategy, score):
        """Genera recomendación textual"""
        if score >= 85:
            return f"Excelente opción {strategy}. Balance óptimo de todos los criterios."
        elif score >= 70:
            return f"Buena opción {strategy}. Cumple bien los objetivos principales."
        elif score >= 60:
            return f"Opción {strategy} aceptable. Algunos aspectos podrían mejorarse."
        else:
            return f"Opción {strategy} básica. Considera ajustar parámetros."
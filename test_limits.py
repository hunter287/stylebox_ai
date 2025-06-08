from color_analysis import ColorAnalyzer
import time

def test_daily_limit():
    analyzer = ColorAnalyzer()
    
    print("=== Тестирование ограничения на количество анализов в день ===")
    
    # Пробуем выполнить 12 анализов (на 2 больше лимита)
    for i in range(12):
        print(f"\nПопытка анализа #{i+1}")
        result = analyzer.analyze_image("test_face.jpg")
        
        if result and "error" in result:
            print(f"Получена ошибка: {result['message']}")
            print(f"Тип ошибки: {result['error']}")
            print(f"Анализов сегодня: {result['analyses_today']}/{result['max_analyses']}")
        else:
            print("Анализ успешно выполнен")
        
        # Небольшая пауза между анализами
        time.sleep(1)

if __name__ == "__main__":
    test_daily_limit() 
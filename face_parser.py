import cv2
import mediapipe as mp
import numpy as np
from collections import Counter

class FaceParser:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            min_detection_confidence=0.5
        )
        
        # Определяем индексы для разных зон лица
        # Контур лица
        self.FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10]
        
        # Глаза
        self.LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33]
        self.RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398, 362]
        
        # Щеки
        self.LEFT_CHEEK = [123, 50, 205, 187, 207, 216, 192, 213, 147, 123]
        self.RIGHT_CHEEK = [352, 376, 411, 434, 416, 433, 376, 352]
        
        # Лоб
        self.FOREHEAD = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10]
        
        # Губы
        self.LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78, 191, 80, 81, 82, 13, 312, 311, 310, 415]

    def get_face_colors(self, image_path):
        """Extract colors from face regions using MediaPipe"""
        # Читаем изображение
        image = cv2.imread(image_path)
        if image is None:
            print(f"Failed to load image: {image_path}")
            return None

        # Конвертируем в RGB для MediaPipe
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width = image.shape[:2]

        # Получаем landmarks лица
        results = self.face_mesh.process(image_rgb)
        if not results.multi_face_landmarks:
            print("No face detected")
            return None

        face_landmarks = results.multi_face_landmarks[0]

        # Определяем регионы для анализа
        regions = {
            'skin': self._get_skin_region(face_landmarks, width, height),
            'eyes': self._get_eyes_region(face_landmarks, width, height),
            'hair': self._get_hair_region(face_landmarks, width, height),
            'lips': self._get_lips_region(face_landmarks, width, height)
        }

        # Анализируем цвета в каждом регионе
        colors = {}
        for region_name, region in regions.items():
            if region is not None:
                color = self._analyze_region_color(image, region)
                if color:
                    colors[region_name] = {
                        'hex': color,
                        'region': region
                    }

        return colors

    def _get_skin_region(self, landmarks, width, height):
        """Get skin region (cheeks and forehead)"""
        # Создаем маску для кожи
        mask = np.zeros((height, width), dtype=np.uint8)
        
        # Добавляем щеки
        for cheek_indices in [self.LEFT_CHEEK, self.RIGHT_CHEEK]:
            points = []
            for idx in cheek_indices:
                if idx < len(landmarks.landmark):
                    point = landmarks.landmark[idx]
                    x, y = int(point.x * width), int(point.y * height)
                    points.append((x, y))
            if points:
                points = np.array(points, dtype=np.int32)
                cv2.fillPoly(mask, [points], 255)
        
        # Добавляем лоб
        points = []
        for idx in self.FOREHEAD:
            if idx < len(landmarks.landmark):
                point = landmarks.landmark[idx]
                x, y = int(point.x * width), int(point.y * height)
                points.append((x, y))
        if points:
            points = np.array(points, dtype=np.int32)
            cv2.fillPoly(mask, [points], 255)
        
        # Исключаем области глаз и губ
        eye_mask = self._get_eyes_region(landmarks, width, height)
        lips_mask = self._get_lips_region(landmarks, width, height)
        
        if eye_mask is not None:
            mask = cv2.bitwise_and(mask, cv2.bitwise_not(eye_mask))
        if lips_mask is not None:
            mask = cv2.bitwise_and(mask, cv2.bitwise_not(lips_mask))
        
        return mask

    def _get_eyes_region(self, landmarks, width, height):
        """Get eyes region"""
        mask = np.zeros((height, width), dtype=np.uint8)
        
        # Добавляем левый и правый глаз
        for eye_indices in [self.LEFT_EYE, self.RIGHT_EYE]:
            points = []
            for idx in eye_indices:
                if idx < len(landmarks.landmark):
                    point = landmarks.landmark[idx]
                    x, y = int(point.x * width), int(point.y * height)
                    points.append((x, y))
            if points:
                points = np.array(points, dtype=np.int32)
                cv2.fillPoly(mask, [points], 255)
        
        # Расширяем маску для захвата радужки
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=2)
        
        return mask

    def _get_lips_region(self, landmarks, width, height):
        """Get lips region"""
        mask = np.zeros((height, width), dtype=np.uint8)
        
        points = []
        for idx in self.LIPS:
            if idx < len(landmarks.landmark):
                point = landmarks.landmark[idx]
                x, y = int(point.x * width), int(point.y * height)
                points.append((x, y))
        
        if points:
            points = np.array(points, dtype=np.int32)
            cv2.fillPoly(mask, [points], 255)
        
        return mask

    def _get_hair_region(self, landmarks, width, height):
        """Get hair region (top of the head)"""
        # Находим верхнюю точку лица
        top_y = min([landmarks.landmark[idx].y for idx in self.FACE_OVAL])
        
        # Создаем маску для верхней части изображения
        mask = np.zeros((height, width), dtype=np.uint8)
        top_y_pixels = int(top_y * height)
        
        # Определяем область волос (верхняя часть изображения)
        hair_height = int(height * 0.3)  # 30% от высоты изображения
        hair_top = max(0, top_y_pixels - hair_height)
        
        # Создаем прямоугольную область для волос
        cv2.rectangle(mask, (0, 0), (width, hair_top), 255, -1)
        
        # Исключаем области лица
        face_mask = np.zeros((height, width), dtype=np.uint8)
        face_points = []
        for idx in self.FACE_OVAL:
            if idx < len(landmarks.landmark):
                point = landmarks.landmark[idx]
                x, y = int(point.x * width), int(point.y * height)
                face_points.append((x, y))
        
        if face_points:
            face_points = np.array(face_points, dtype=np.int32)
            cv2.fillPoly(face_mask, [face_points], 255)
            mask = cv2.bitwise_and(mask, cv2.bitwise_not(face_mask))
        
        return mask

    def _analyze_region_color(self, image, mask):
        """Analyze dominant color in the region using NumPy"""
        # Применяем маску к изображению
        masked_image = cv2.bitwise_and(image, image, mask=mask)
        
        # Получаем все ненулевые пиксели с помощью NumPy
        pixels = masked_image[mask > 0]
        if len(pixels) == 0:
            return None

        # Конвертируем в RGB и меняем форму массива
        pixels_rgb = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2RGB)
        pixels_rgb = pixels_rgb.reshape(-1, 3)  # Преобразуем в 2D массив (N, 3)
        
        # Используем NumPy для фильтрации цветов
        # Исключаем слишком светлые и тёмные цвета
        is_not_white = ~np.all(pixels_rgb > 240, axis=1)
        is_not_black = ~np.all(pixels_rgb < 20, axis=1)
        valid_pixels = pixels_rgb[is_not_white & is_not_black]
        
        if len(valid_pixels) == 0:
            return None
            
        # Находим доминирующий цвет с помощью NumPy
        # Группируем похожие цвета (с допуском 10)
        color_bins = (valid_pixels // 10) * 10
        unique_colors, counts = np.unique(color_bins, axis=0, return_counts=True)
        dominant_color = unique_colors[np.argmax(counts)]
        
        # Конвертируем в HEX
        hex_color = '#{:02x}{:02x}{:02x}'.format(*dominant_color)
        
        return hex_color 
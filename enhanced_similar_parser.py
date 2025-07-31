#!/usr/bin/env python3
"""
Улучшенный парсер визуально похожих товаров с Lamoda
Использует лучшие практики из существующих парсеров
"""

import asyncio
import random
import re
from playwright.async_api import async_playwright
from mongo_config import mongo_config
from datetime import datetime

class EnhancedSimilarParser:
    def __init__(self):
        self.browser = None
        self.page = None
        self.collection_name = "products_enhanced"
    
    async def start_browser(self):
        """Запускает браузер с подключением к существующему Chrome"""
        try:
            self.playwright = await async_playwright().start()
            
            # Подключаемся к существующему Chrome через CDP
            self.browser = await self.playwright.chromium.connect_over_cdp("http://localhost:9222")
            
            # Создаем новую страницу
            self.page = await self.browser.new_page()
            
            # Устанавливаем User-Agent
            await self.page.set_extra_http_headers({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            print("✅ Браузер подключен")
            return True
            
        except Exception as e:
            print(f"❌ Ошибка подключения к браузеру: {e}")
            return False
    
    async def simulate_human_behavior(self):
        """Имитирует человеческое поведение"""
        try:
            # Случайные движения мыши
            await self.page.mouse.move(
                random.randint(100, 800),
                random.randint(100, 600)
            )
            
            # Случайная прокрутка
            await self.page.evaluate(f"window.scrollBy(0, {random.randint(100, 300)});")
            
            # Пауза
            await asyncio.sleep(random.uniform(1, 3))
            
        except Exception as e:
            print(f"⚠️ Ошибка имитации поведения: {e}")
    
    async def find_visual_similar_products(self, source_url):
        """Находит визуально похожие товары, нажимая кнопку 'Визуально' и прокручивая карусель"""
        try:
            print(f"🔍 Ищем визуально похожие товары на странице: {source_url}")
            
            # Загружаем страницу исходного товара с увеличенным таймаутом
            await self.page.goto(source_url, wait_until="load", timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Имитируем человеческое поведение
            await self.simulate_human_behavior()
            
            # Прокручиваем страницу для загрузки похожих товаров
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
            await asyncio.sleep(2)
            
            # Ищем кнопку "Визуально" в разделе похожих товаров
            visual_button_selectors = [
                "div.swiper-slide[role='button']:has-text('Визуально')",
                "div[role='button']:has-text('Визуально')",
                ".swiper-slide:has-text('Визуально')",
                "div:has-text('Визуально')"
            ]
            
            visual_button = None
            for selector in visual_button_selectors:
                try:
                    visual_button = await self.page.query_selector(selector)
                    if visual_button:
                        print(f"🔍 Найдена кнопка 'Визуально' с селектором: {selector}")
                        break
                except:
                    continue
            
            if not visual_button:
                print("❌ Кнопка 'Визуально' не найдена")
                return []
            
            # Нажимаем на кнопку "Визуально"
            print("🖱️ Нажимаем на кнопку 'Визуально'...")
            await visual_button.click()
            await asyncio.sleep(3)  # Ждем загрузки визуально похожих товаров
            
            # Проверяем, что кнопка "Визуально" стала активной
            try:
                active_visual_button = await self.page.query_selector("div.swiper-slide[role='button'][class*='active']:has-text('Визуально')")
                if active_visual_button:
                    print("✅ Кнопка 'Визуально' активирована")
                else:
                    print("⚠️ Кнопка 'Визуально' не активирована, но продолжаем...")
            except:
                print("⚠️ Не удалось проверить активацию кнопки 'Визуально'")
            
            # Ищем стрелку "следующая" для прокрутки карусели
            next_arrow_selectors = [
                "div.swiper-arrow-prefix__similar._swiper-arrow-prefix__pp-premium_1m0yv_152._arrow_1m0yv_71._arrow_next_1m0yv_144",
                ".swiper-arrow-prefix__similar._arrow_next",
                "div[class*='swiper-arrow'][class*='arrow_next']",
                ".swiper-arrow-next",
                "[class*='arrow'][class*='next']"
            ]
            
            next_arrow = None
            for selector in next_arrow_selectors:
                try:
                    next_arrow = await self.page.query_selector(selector)
                    if next_arrow:
                        print(f"🔍 Найдена стрелка 'следующая' с селектором: {selector}")
                        break
                except:
                    continue
            
            if not next_arrow:
                print("❌ Стрелка 'следующая' не найдена")
                return []
            
            # Собираем все визуально похожие товары
            similar_products = []
            max_groups = 4  # Максимум 4 группы по 6 товаров
            
            for group in range(max_groups):
                print(f"📦 Обрабатываем группу {group + 1}/{max_groups}")
                
                # Ждем загрузки товаров в текущей группе
                await asyncio.sleep(2)
                
                # Ищем ссылки на товары в текущей группе - более специфичные селекторы
                product_selectors = [
                    ".swiper-slide a[href*='/p/']",  # Товары в слайдере
                    ".ui-recommendation-product a[href*='/p/']",  # Рекомендуемые товары
                    "a[href*='/p/'][class*='productCard']",  # Карточки товаров
                    ".similar-products a[href*='/p/']",  # Похожие товары
                    ".recommendations a[href*='/p/']"  # Рекомендации
                ]
                
                group_products = []
                for selector in product_selectors:
                    try:
                        elements = await self.page.query_selector_all(selector)
                        if elements:
                            for element in elements:
                                href = await element.get_attribute('href')
                                if href and '/p/' in href:
                                    # Извлекаем ID товара из URL
                                    product_id_match = re.search(r'/p/([^/?]+)', href)
                                    if product_id_match:
                                        product_id = product_id_match.group(1)
                                        full_url = f"https://lamoda.ru/p/{product_id}/"
                                        
                                        # Проверяем, что это не тот же товар и не дубликат
                                        if (full_url != source_url and 
                                            full_url not in similar_products and 
                                            full_url not in group_products):
                                            group_products.append(full_url)
                                            print(f"   ✅ Найден товар в группе {group + 1}: {full_url}")
                            break  # Если нашли товары, прекращаем поиск
                    except Exception as e:
                        print(f"   ⚠️ Ошибка с селектором {selector}: {e}")
                        continue
                
                # Проверяем, что мы нашли товары именно в разделе визуально похожих
                if group_products:
                    # Ограничиваем количество товаров в группе до 6 (как должно быть)
                    group_products = group_products[:6]
                    similar_products.extend(group_products)
                    print(f"   📊 В группе {group + 1} найдено товаров: {len(group_products)}")
                else:
                    print(f"   ⚠️ В группе {group + 1} товары не найдены")
                
                # Если это не последняя группа, нажимаем на стрелку
                if group < max_groups - 1:
                    try:
                        print(f"   ➡️ Переходим к следующей группе...")
                        await next_arrow.click()
                        await asyncio.sleep(2)  # Ждем загрузки следующей группы
                    except Exception as e:
                        print(f"   ❌ Ошибка перехода к следующей группе: {e}")
                        break
            
            print(f"📊 Всего найдено визуально похожих товаров: {len(similar_products)}")
            return similar_products
            
        except Exception as e:
            print(f"❌ Ошибка поиска визуально похожих товаров: {e}")
            return []

    async def extract_name(self):
        """Извлекает название товара используя логику из similar_products_expander_v2.py"""
        try:
            selectors = [
                "h1[data-testid='product-title']",
                ".product-title",
                "h1.product-name",
                "[data-testid='product-name']",
                ".product-name",
                "h1",
                ".title",
                "[class*='title']"
            ]
            
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        name = await element.text_content()
                        if name and len(name.strip()) > 2:
                            name = name.strip()
                            print(f"   📝 Найдено название: {name}")
                            return name
                except:
                    continue
            
            print("   ⚠️ Название не найдено")
            return ""
            
        except Exception as e:
            print(f"   ❌ Ошибка извлечения названия: {e}")
            return ""
    
    async def extract_brand(self):
        """Извлекает бренд используя логику из similar_products_expander_v2.py"""
        try:
            selectors = [
                "a[data-testid='brand-link']",
                ".brand-link",
                ".product-brand",
                "a[href*='/brand/']",
                ".brand-name",
                "[data-testid='brand']",
                "[class*='brand']"
            ]
            
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        brand = await element.text_content()
                        if brand and len(brand.strip()) > 1:
                            brand = brand.strip()
                            print(f"   🏷️ Найден бренд: {brand}")
                            return brand
                except:
                    continue
            
            print("   ⚠️ Бренд не найден")
            return ""
            
        except Exception as e:
            print(f"   ❌ Ошибка извлечения бренда: {e}")
            return ""
    
    async def extract_price(self):
        """Извлекает цену используя логику из similar_products_expander_v2.py"""
        try:
            # Приоритетные селекторы из price_parser.py
            selectors = [
                "span[aria-label='Итоговая цена']",
                "span._price_g09b8_11",
                ".ui-product-price ._price_g09b8_11",
                "[class*='price']",
                "[data-testid='price']",
                ".price",
                ".product-price",
                ".price-current"
            ]
            
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        price_text = await element.text_content()
                        if price_text:
                            # Используем regex из price_parser.py
                            price_match = re.search(r'(\d+(?:\s\d+)*)', price_text.replace(' ', ''))
                            if price_match:
                                price_value = int(price_match.group(1).replace(' ', ''))
                                print(f"   💰 Найдена цена: {price_text}")
                                print(f"   ✅ Извлечена цена: {price_value}")
                                return price_value
                except:
                    continue
            
            # Fallback: ищем цену в тексте страницы
            try:
                content = await self.page.content()
                price_matches = re.findall(r'(\d+)\s*₽', content)
                if price_matches:
                    price_value = int(price_matches[0])
                    print(f"   ✅ Цена найдена в тексте: {price_value}")
                    return price_value
                
                price_matches = re.findall(r'(\d+)\s*руб', content)
                if price_matches:
                    price_value = int(price_matches[0])
                    print(f"   ✅ Цена найдена в тексте: {price_value}")
                    return price_value
            except:
                pass
            
            print("   ⚠️ Цена не найдена")
            return 0
            
        except Exception as e:
            print(f"   ❌ Ошибка извлечения цены: {e}")
            return 0
    
    async def extract_image(self):
        """Извлекает URL изображения используя логику из similar_products_expander_v2.py"""
        try:
            # Ищем первое изображение в галерее как в image_parser.py
            selector = 'div.ui-product-page-gallery img._root_1wiwn_3._image_1v0jy_2'
            
            element = await self.page.query_selector(selector)
            if element:
                src = await element.get_attribute('src')
                if src:
                    # Преобразуем относительный URL в абсолютный
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://www.lamoda.ru' + src
                    
                    print(f"   🖼️ Найдено изображение: {src}")
                    return src
                else:
                    print(f"   ⚠️ Атрибут src не найден")
            
            # Альтернативные селекторы для изображений как в image_parser.py
            alternative_selectors = [
                'img._root_1wiwn_3._image_1v0jy_2',
                '.ui-product-page-gallery img',
                '.product-gallery img',
                '.product-image img',
                'img[data-testid="product-image"]',
                '.gallery img',
                'img[alt*="товар"]',
                'img[alt*="product"]',
                "img[data-testid='product-image']",
                ".product-image img",
                ".gallery img",
                "[data-testid='gallery-image']",
                "img[alt*='товар']",
                ".product-photo img",
                "[class*='image'] img",
                "[class*='photo'] img"
            ]
            
            for alt_selector in alternative_selectors:
                try:
                    elements = await self.page.query_selector_all(alt_selector)
                    for element in elements:
                        src = await element.get_attribute('src')
                        if src and ('lmcdn.ru' in src or 'img600x866' in src or 'img389x562' in src):
                            # Преобразуем относительный URL в абсолютный
                            if src.startswith('//'):
                                src = 'https:' + src
                            elif src.startswith('/'):
                                src = 'https://www.lamoda.ru' + src
                            
                            print(f"   🖼️ Найдено изображение (альтернативный селектор): {src}")
                            return src
                except:
                    continue
            
            print("   ⚠️ Изображение не найдено")
            return ""
            
        except Exception as e:
            print(f"   ⚠️ Ошибка поиска изображения: {e}")
            return ""
    
    async def extract_category(self):
        """Извлекает категорию используя логику из similar_products_expander_v2.py"""
        try:
            # Ищем все хлебные крошки как в category_parser.py
            selectors = [
                "a[href*='/c/'][class*='breadcrumbs']",
                ".breadcrumbs a[href*='/c/']",
                "a[href*='/c/'][title]",
                ".breadcrumb a[href*='/c/']",
                "nav a[href*='/c/']",
                ".breadcrumbs__item a",
                "[data-testid='breadcrumb'] a",
                ".breadcrumb-item a"
            ]
            
            all_categories = []
            
            for selector in selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements:
                        for element in elements:
                            category_text = await element.text_content()
                            if category_text:
                                category_text = category_text.strip()
                                if category_text and len(category_text) > 1:
                                    all_categories.append(category_text)
                        break  # Если нашли элементы, прекращаем поиск
                except:
                    continue
            
            print(f"   📋 Все найденные категории: {all_categories}")
            
            # Исключаем общие категории и фильтры как в category_parser.py
            excluded_categories = [
                'женщинам', 'мужчинам', 'детям', 'одежда', 'обувь', 'аксессуары',
                'одежда больших размеров', 'большие размеры', 'плюс сайз',
                'новинки', 'распродажа', 'скидки', 'акции', 'идеи'
            ]
            
            # Фильтруем категории, исключая ненужные
            filtered_categories = []
            for category in all_categories:
                category_lower = category.lower()
                if category_lower not in excluded_categories:
                    filtered_categories.append(category)
            
            print(f"   🔍 Отфильтрованные категории: {filtered_categories}")
            
            # Берем первую отфильтрованную категорию как основную
            if filtered_categories:
                main_category = filtered_categories[0]
                print(f"   ✅ Найдена основная категория: {main_category}")
                return main_category.lower()
            
            # Если отфильтрованных нет, берем предпоследнюю (обычно это подкатегория)
            if len(all_categories) >= 2:
                specific_category = all_categories[-2]  # Предпоследняя
                print(f"   ✅ Используем предпоследнюю категорию: {specific_category}")
                return specific_category.lower()
            
            # Если ничего не нашли, возвращаем пустую строку
            print("   ⚠️ Специфичная категория не найдена")
            return ""
            
        except Exception as e:
            print(f"   ❌ Ошибка извлечения категории: {e}")
            return ""
    
    async def extract_subcategory(self):
        """Извлекает подкатегорию используя логику из similar_products_expander_v2.py"""
        try:
            # Ищем все хлебные крошки как в category_parser.py
            selectors = [
                "a[href*='/c/'][class*='breadcrumbs']",
                ".breadcrumbs a[href*='/c/']",
                "a[href*='/c/'][title]",
                ".breadcrumb a[href*='/c/']",
                "nav a[href*='/c/']",
                ".breadcrumbs__item a",
                "[data-testid='breadcrumb'] a",
                ".breadcrumb-item a"
            ]
            
            all_categories = []
            
            for selector in selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements:
                        for element in elements:
                            category_text = await element.text_content()
                            if category_text:
                                category_text = category_text.strip()
                                if category_text and len(category_text) > 1:
                                    all_categories.append(category_text)
                        break  # Если нашли элементы, прекращаем поиск
                except:
                    continue
            
            # Исключаем общие категории и фильтры как в category_parser.py
            excluded_categories = [
                'женщинам', 'мужчинам', 'детям', 'одежда', 'обувь', 'аксессуары',
                'одежда больших размеров', 'большие размеры', 'плюс сайз',
                'новинки', 'распродажа', 'скидки', 'акции', 'идеи'
            ]
            
            # Фильтруем категории, исключая ненужные
            filtered_categories = []
            for category in all_categories:
                category_lower = category.lower()
                if category_lower not in excluded_categories:
                    filtered_categories.append(category)
            
            # Берем предпоследнюю отфильтрованную категорию (как в category_parser.py)
            if len(filtered_categories) >= 2:
                subcategory = filtered_categories[-2]  # Предпоследняя
                print(f"   ✅ Найдена подкатегория (предпоследняя): {subcategory}")
                return subcategory.lower()
            elif filtered_categories:
                # Если только одна отфильтрованная категория, берем её
                subcategory = filtered_categories[0]
                print(f"   ✅ Используем единственную отфильтрованную категорию: {subcategory}")
                return subcategory.lower()
            
            # Если отфильтрованных нет, берем предпоследнюю из всех
            if len(all_categories) >= 2:
                subcategory = all_categories[-2]  # Предпоследняя
                print(f"   ✅ Используем предпоследнюю категорию из всех: {subcategory}")
                return subcategory.lower()
            elif all_categories:
                # Если только одна категория, берем её
                subcategory = all_categories[0]
                print(f"   ✅ Используем единственную категорию: {subcategory}")
                return subcategory.lower()
            
            print("   ⚠️ Подкатегория не найдена")
            return ""
            
        except Exception as e:
            print(f"   ❌ Ошибка извлечения подкатегории: {e}")
            return ""
    
    async def extract_description(self):
        """Извлекает характеристики товара как в similar_products_expander_v2.py"""
        try:
            print("   📝 Ищем характеристики товара...")
            
            # Ищем все элементы с характеристиками как в description_parser.py
            attribute_items = await self.page.query_selector_all('p._item_cdxgk_2')
            
            if not attribute_items:
                # Альтернативные селекторы для характеристик
                attribute_items = await self.page.query_selector_all('[class*="characteristics"] [class*="item"]')
            
            if not attribute_items:
                attribute_items = await self.page.query_selector_all('[class*="attributes"] [class*="item"]')
            
            if not attribute_items:
                attribute_items = await self.page.query_selector_all('[class*="details"] [class*="item"]')
            
            if not attribute_items:
                attribute_items = await self.page.query_selector_all('[class*="features"] [class*="item"]')
            
            if not attribute_items:
                # Ищем любые элементы с характеристиками
                attribute_items = await self.page.query_selector_all('p[class*="item"]')
            
            if not attribute_items:
                # Ищем в таблицах характеристик
                attribute_items = await self.page.query_selector_all('tr[class*="row"]')
            
            if not attribute_items:
                # Ищем в списках характеристик
                attribute_items = await self.page.query_selector_all('li[class*="item"]')
            
            if not attribute_items:
                # Ищем в div с характеристиками
                attribute_items = await self.page.query_selector_all('div[class*="item"]')
            
            print(f"   🔍 Найдено элементов характеристик: {len(attribute_items)}")
            
            attributes = {}
            
            for item in attribute_items:
                try:
                    # Извлекаем название характеристики
                    name_element = await item.query_selector('span[class*="attributeName"], span[class*="name"], span[class*="label"]')
                    if not name_element:
                        # Ищем в других элементах
                        name_element = await item.query_selector('td:first-child, th, strong, b')
                    
                    if not name_element:
                        # Ищем любой элемент с текстом
                        name_element = item
                    
                    attribute_name = await name_element.text_content()
                    if not attribute_name:
                        continue
                    
                    attribute_name = attribute_name.strip()
                    
                    # Извлекаем значение характеристики
                    value_element = await item.query_selector('span[class*="value"], span[class*="content"], td:last-child')
                    if not value_element:
                        # Ищем в других элементах
                        value_element = await item.query_selector('span, div, p')
                    
                    if not value_element:
                        # Берем весь текст элемента
                        value_element = item
                    
                    attribute_value = await value_element.text_content()
                    if not attribute_value:
                        continue
                    
                    attribute_value = attribute_value.strip()
                    
                    # Очищаем название от лишних символов
                    import re
                    attribute_name = re.sub(r'[^\w\s\-%]', '', attribute_name).strip()
                    
                    # Очищаем значение от лишних символов
                    attribute_value = re.sub(r'[^\w\s\-%.,]', '', attribute_value).strip()
                    
                    # Добавляем в словарь только если есть и название, и значение
                    if attribute_name and attribute_value and len(attribute_name) > 1 and len(attribute_value) > 1:
                        attributes[attribute_name] = attribute_value
                        print(f"   🔍 {attribute_name}: {attribute_value}")
                    
                except Exception as e:
                    print(f"   ❌ Ошибка при обработке характеристики: {e}")
                    continue
            
            # Если нашли характеристики, возвращаем как объект
            if attributes:
                print(f"   ✅ Найдено характеристик: {len(attributes)}")
                return attributes
            
            # Если характеристики не найдены, ищем обычное описание
            print("   ⚠️ Характеристики не найдены, ищем обычное описание...")
            
            selectors = [
                "[data-testid='product-description']",
                ".product-description",
                ".description",
                ".product-details",
                "[data-testid='description']",
                ".product-info .text",
                "[class*='description']",
                "[class*='details']"
            ]
            
            for selector in selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        description = await element.text_content()
                        if description and len(description.strip()) > 20:
                            description = description.strip()[:500]  # Ограничиваем длину
                            print(f"   📝 Найдено описание: {description[:100]}...")
                            return description
                except:
                    continue
            
            print("   ⚠️ Описание не найдено")
            return ""
            
        except Exception as e:
            print(f"   ❌ Ошибка извлечения описания: {e}")
            return ""
    
    async def extract_sizes(self):
        """Извлекает размеры используя логику из similar_products_expander_v2.py"""
        try:
            print("   📏 Ищем размеры...")
            
            # Ждем загрузки страницы
            await asyncio.sleep(2)
            
            # Ищем селектор размеров - расширенный список
            size_selectors = [
                "._dropdown_14ecl_124",
                ".ui-product-page-sizes-chooser",
                "[class*='sizes-chooser']",
                "[class*='dropdown']",
                ".product-sizes",
                ".size-selector",
                "[data-testid='sizes-chooser']",
                ".sizes-dropdown"
            ]
            
            size_element = None
            for selector in size_selectors:
                try:
                    size_element = await self.page.query_selector(selector)
                    if size_element:
                        print(f"   🔍 Найден селектор размеров: {selector}")
                        break
                except:
                    continue
            
            if not size_element:
                print("   ❌ Не найден селектор размеров")
                return {"Российский": [], "Производителя": []}
            
            # Извлекаем размеры с новой логикой
            sizes_data = await self.extract_sizes_new_logic(size_element)
            
            if sizes_data:
                print(f"   ✅ Извлечены размеры: {sizes_data}")
                return sizes_data
            
            return {"Российский": [], "Производителя": []}
            
        except Exception as e:
            print(f"   ❌ Ошибка извлечения размеров: {e}")
            return {"Российский": [], "Производителя": []}
    
    async def extract_sizes_new_logic(self, size_element):
        """Новая логика извлечения размеров из similar_products_expander_v2.py"""
        try:
            # Инициализируем структуру данных
            sizes_data = {"Российский": [], "Производителя": []}
            
            # Ищем все элементы с размерами
            size_items = await size_element.query_selector_all("[class*='colspan']")
            if not size_items:
                size_items = await size_element.query_selector_all("[class*='sizes-chooser-item']")
            if not size_items:
                size_items = await size_element.query_selector_all(".size-item")
            if not size_items:
                size_items = await size_element.query_selector_all("div[class*='item']")
            
            print(f"   🔍 Найдено элементов размеров: {len(size_items)}")
            
            for i, item in enumerate(size_items):
                try:
                    # Получаем весь текст элемента
                    item_text = await item.text_content()
                    if not item_text or not item_text.strip():
                        continue
                    
                    # Ищем строки с размерами внутри элемента
                    rows = await item.query_selector_all("div")
                    
                    # Если не нашли div, ищем span
                    if not rows:
                        rows = await item.query_selector_all("span")
                    
                    # Если не нашли span, ищем любые элементы
                    if not rows:
                        rows = await item.query_selector_all("*")
                    
                    # Обрабатываем каждую строку
                    for j, row in enumerate(rows):
                        try:
                            row_text = await row.text_content()
                            if not row_text or not row_text.strip():
                                continue
                            
                            cleaned_text = self.clean_size_text(row_text.strip())
                            if not cleaned_text:
                                continue
                            
                            # Определяем тип размера
                            if self.is_russian_size(cleaned_text):
                                if cleaned_text not in sizes_data["Российский"]:
                                    sizes_data["Российский"].append(cleaned_text)
                            elif self.is_manufacturer_size(cleaned_text):
                                if cleaned_text not in sizes_data["Производителя"]:
                                    sizes_data["Производителя"].append(cleaned_text)
                            else:
                                # Если не определили тип, но размер содержит буквы - это производитель
                                if any(char.isalpha() for char in cleaned_text):
                                    # Проверяем, не содержит ли размер цифры (если да, то это комбинированный размер)
                                    if any(char.isdigit() for char in cleaned_text):
                                        # Проверяем, не является ли это размером производителя с цифрами (например, 38/164 EUR)
                                        if re.match(r'^\d+/\d+\s*[A-Z]+$', cleaned_text):
                                            if cleaned_text not in sizes_data["Производителя"]:
                                                sizes_data["Производителя"].append(cleaned_text)
                                        else:
                                            # Это комбинированный размер, пропускаем
                                            pass
                                    else:
                                        if cleaned_text not in sizes_data["Производителя"]:
                                            sizes_data["Производителя"].append(cleaned_text)
                                # Если содержит только цифры и слеши - это российский
                                elif any(char.isdigit() for char in cleaned_text):
                                    if cleaned_text not in sizes_data["Российский"]:
                                        sizes_data["Российский"].append(cleaned_text)
                                # Если содержит и цифры, и буквы - это комбинированный размер, пропускаем
                                elif any(char.isdigit() for char in cleaned_text) and any(char.isalpha() for char in cleaned_text):
                                    pass
                            
                        except Exception as e:
                            continue
                
                except Exception as e:
                    continue
            
            # Проверяем результат
            has_russian = len(sizes_data["Российский"]) > 0
            has_manufacturer = len(sizes_data["Производителя"]) > 0
            
            if has_russian or has_manufacturer:
                return sizes_data
            
            return None
            
        except Exception as e:
            print(f"   ❌ Ошибка новой логики извлечения: {e}")
            return None
    
    def is_russian_size(self, text):
        """Определяет, является ли размер российским"""
        if not text:
            return False
        
        # Российские размеры обычно содержат цифры и могут содержать слеши
        russian_patterns = [
            r'^\d+$',  # Просто цифры: 40, 42
            r'^\d+/\d+$',  # Слеш: 40/42
            r'^\d+-\d+$',  # Дефис: 40-42
            r'^\d+\s*-\s*\d+$',  # Дефис с пробелами: 40 - 42
            r'^\d+\s*/\s*\d+$',  # Слеш с пробелами: 40 / 42
        ]
        
        for pattern in russian_patterns:
            if re.match(pattern, text):
                return True
        
        return False
    
    def is_manufacturer_size(self, text):
        """Определяет, является ли размер размером производителя"""
        if not text:
            return False
        
        # Размеры производителя обычно содержат буквы
        manufacturer_patterns = [
            r'^[A-Z]+$',  # Только буквы: XS, S, M, L, XL, XXL
            r'^[A-Z]+\d+$',  # Буквы + цифры: L42, XL44
            r'^\d+[A-Z]+$',  # Цифры + буквы: 42L, 44XL
            r'^[A-Z]+\d+[A-Z]+$',  # Буквы + цифры + буквы: L42XL
            r'^[A-Z]+/[A-Z]+$',  # Буквы через слеш: XS/S, M/L
            r'^[A-Z]+\s*/\s*[A-Z]+$',  # Буквы через слеш с пробелами: XS / S, M / L
            r'^\d+/\d+\s+[A-Z]+$',  # Цифры/цифры + буквы: 38/164 EUR
            r'^\d+/\d+[A-Z]+$',  # Цифры/цифры + буквы без пробела: 38/164EUR
        ]
        
        # Проверяем, содержит ли текст буквы
        has_letters = any(char.isalpha() for char in text)
        
        if has_letters:
            for pattern in manufacturer_patterns:
                if re.match(pattern, text):
                    return True
        
        return False
    
    def clean_size_text(self, text):
        """Очищает текст размера от лишних символов"""
        if not text:
            return None
        
        # Удаляем суффиксы RUS, INT и другие
        cleaned = text.strip()
        cleaned = cleaned.replace(" RUS", "").replace(" INT", "")
        cleaned = cleaned.replace("RUS", "").replace("INT", "")
        
        # Удаляем лишние пробелы и символы
        cleaned = " ".join(cleaned.split())
        
        # Удаляем скобки и их содержимое
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)
        
        # Удаляем лишние символы, но сохраняем буквы, цифры, слеши и дефисы
        cleaned = re.sub(r'[^\w\s/\-]', '', cleaned)
        
        # Удаляем лишние пробелы
        cleaned = " ".join(cleaned.split())
        
        # Проверяем, что размер не пустой и имеет смысл
        if cleaned and len(cleaned) > 0:
            return cleaned.upper()  # Приводим к верхнему регистру
        
        return None
    
    async def extract_product_data(self, url):
        """Извлекает все данные товара"""
        try:
            print(f"🔍 Парсим товар: {url}")
            
            # Загружаем страницу товара с увеличенным таймаутом
            await self.page.goto(url, wait_until="load", timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))
            
            # Имитируем человеческое поведение
            await self.simulate_human_behavior()
            
            # Извлекаем все данные
            product_data = {
                'name': await self.extract_name(),
                'brand': await self.extract_brand(),
                'price': await self.extract_price(),
                'currency': '₽',
                'imageUrl': await self.extract_image(),
                'category': await self.extract_category(),
                'subcategory': await self.extract_subcategory(),
                'description': await self.extract_description(),
                'sizes': await self.extract_sizes(),
                'status': 'available',
                'url': url,
                'createdAt': datetime.now(),
                'updatedAt': datetime.now(),
                'source': 'lamoda'
            }
            
            return product_data
            
        except Exception as e:
            print(f"❌ Ошибка извлечения данных товара: {e}")
            return None
    
    async def process_source_product(self, source_url):
        """Обрабатывает один исходный товар и находит до 24 визуально похожих"""
        try:
            print(f"\n📦 Обрабатываем исходный товар: {source_url}")
            
            # Находим визуально похожие товары
            similar_urls = await self.find_visual_similar_products(source_url)
            
            if not similar_urls:
                print("❌ Визуально похожие товары не найдены")
                return 0
            
            print(f"🎯 Найдено {len(similar_urls)} визуально похожих товаров")
            
            added_count = 0
            skipped_duplicates = 0
            skipped_errors = 0
            
            for i, similar_url in enumerate(similar_urls, 1):
                try:
                    print(f"\n🔄 Обрабатываем похожий товар {i}/{len(similar_urls)}: {similar_url}")
                    
                    # Проверяем, не существует ли уже такой товар в коллекции products_enhanced
                    existing_product = mongo_config.collection_enhanced.find_one({'url': similar_url})
                    if existing_product:
                        print(f"   ⚠️ Товар уже существует в коллекции products_enhanced: {similar_url}")
                        print(f"      Название: {existing_product.get('name', 'N/A')}")
                        skipped_duplicates += 1
                        continue
                    
                    # Извлекаем данные похожего товара
                    similar_product_data = await self.extract_product_data(similar_url)
                    
                    if not similar_product_data:
                        print(f"   ❌ Не удалось извлечь данные похожего товара: {similar_url}")
                        skipped_errors += 1
                        continue
                    
                    # Проверяем дубликаты по названию и бренду
                    product_name = similar_product_data.get('name', '').strip()
                    product_brand = similar_product_data.get('brand', '').strip()
                    
                    if product_name and product_brand:
                        # Проверяем в коллекции products_enhanced
                        duplicate_in_enhanced = mongo_config.collection_enhanced.find_one({
                            'name': product_name,
                            'brand': product_brand
                        })
                        if duplicate_in_enhanced:
                            print(f"   ⚠️ Дубликат по названию и бренду в products_enhanced:")
                            print(f"      Название: {product_name}")
                            print(f"      Бренд: {product_brand}")
                            print(f"      Существующий URL: {duplicate_in_enhanced.get('url', 'N/A')}")
                            skipped_duplicates += 1
                            continue
                    
                    # Добавляем товар в коллекцию products_enhanced
                    result = mongo_config.collection_enhanced.insert_one(similar_product_data)
                    
                    if result.inserted_id:
                        print(f"   ✅ Похожий товар успешно добавлен в базу данных")
                        print(f"      Название: {similar_product_data['name']}")
                        print(f"      Бренд: {similar_product_data['brand']}")
                        print(f"      Цена: {similar_product_data['price']} ₽")
                        print(f"      Категория: {similar_product_data['category']}")
                        print(f"      Подкатегория: {similar_product_data['subcategory']}")
                        print(f"      Изображение: {similar_product_data['imageUrl']}")
                        added_count += 1
                    else:
                        print(f"   ❌ Ошибка добавления товара в базу данных: {similar_url}")
                    
                    # Пауза между товарами
                    if i < len(similar_urls):
                        pause = random.uniform(2, 4)
                        print(f"   ⏸️ Пауза {pause:.1f}с перед следующим товаром...")
                        await asyncio.sleep(pause)
                    
                except Exception as e:
                    print(f"   ❌ Ошибка обработки похожего товара {i}: {e}")
                    skipped_errors += 1
                    continue
            
            print(f"\n📊 Результат обработки исходного товара:")
            print(f"   Обработано похожих товаров: {len(similar_urls)}")
            print(f"   ✅ Добавлено новых товаров: {added_count}")
            print(f"   ⚠️ Пропущено дубликатов: {skipped_duplicates}")
            print(f"   ❌ Пропущено ошибок: {skipped_errors}")
            print(f"   📈 Эффективность: {(added_count / len(similar_urls) * 100):.1f}%")
            
            return added_count
            
        except Exception as e:
            print(f"❌ Ошибка обработки исходного товара: {e}")
            return 0

    async def process_source_product_with_attributes(self, source_url, color_types, kibbe_types, body_types, heights):
        """Обрабатывает исходный товар и находит визуально похожие товары с копированием атрибутов"""
        try:
            print(f"\n📦 Обрабатываем исходный товар с атрибутами: {source_url}")
            
            # Сначала парсим и добавляем исходный товар
            print(f"🔍 Парсим исходный товар: {source_url}")
            source_product_data = await self.extract_product_data(source_url)
            
            if not source_product_data:
                print("❌ Не удалось спарсить исходный товар")
                return 0
            
            # Добавляем атрибуты из Excel к исходному товару
            source_product_data['colorTypes'] = color_types
            source_product_data['kibbeTypes'] = kibbe_types
            source_product_data['bodyTypes'] = body_types
            source_product_data['heights'] = heights
            source_product_data['source'] = 'excel_source_product'
            
            # Проверяем, не существует ли уже такой товар в коллекции products_enhanced
            existing_product = mongo_config.collection_enhanced.find_one({'url': source_url})
            if existing_product:
                print(f"⚠️ Исходный товар уже существует в коллекции products_enhanced")
                print(f"   Название: {existing_product.get('name', 'N/A')}")
            else:
                # Добавляем исходный товар в коллекцию products_enhanced
                result = mongo_config.collection_enhanced.insert_one(source_product_data)
                if result.inserted_id:
                    print(f"✅ Исходный товар добавлен в базу данных")
                    print(f"   Название: {source_product_data['name']}")
                    print(f"   Бренд: {source_product_data['brand']}")
                    print(f"   Цена: {source_product_data['price']} ₽")
                    print(f"   Категория: {source_product_data['category']}")
                    print(f"   Подкатегория: {source_product_data['subcategory']}")
                    print(f"   Изображение: {source_product_data['imageUrl']}")
                    print(f"   Цветотипы: {color_types}")
                    print(f"   Типы Киббе: {kibbe_types}")
                    print(f"   Типы телосложения: {body_types}")
                    print(f"   Росты: {heights}")
                else:
                    print("❌ Ошибка добавления исходного товара")
                    return 0
            
            # Находим визуально похожие товары
            similar_urls = await self.find_visual_similar_products(source_url)
            
            if not similar_urls:
                print("❌ Визуально похожие товары не найдены")
                return 0
            
            print(f"🎯 Найдено {len(similar_urls)} визуально похожих товаров")
            
            added_count = 0
            skipped_duplicates = 0
            skipped_errors = 0
            
            for i, similar_url in enumerate(similar_urls, 1):
                try:
                    print(f"\n🔄 Обрабатываем похожий товар {i}/{len(similar_urls)}: {similar_url}")
                    
                    # Проверяем, не существует ли уже такой товар в коллекции products_enhanced
                    existing_product = mongo_config.collection_enhanced.find_one({'url': similar_url})
                    if existing_product:
                        print(f"   ⚠️ Товар уже существует в коллекции products_enhanced: {similar_url}")
                        print(f"      Название: {existing_product.get('name', 'N/A')}")
                        skipped_duplicates += 1
                        continue
                    
                    # Извлекаем данные похожего товара
                    similar_product_data = await self.extract_product_data(similar_url)
                    
                    if not similar_product_data:
                        print(f"   ❌ Не удалось извлечь данные похожего товара: {similar_url}")
                        skipped_errors += 1
                        continue
                    
                    # Копируем атрибуты из исходного товара
                    similar_product_data['colorTypes'] = color_types
                    similar_product_data['kibbeTypes'] = kibbe_types
                    similar_product_data['bodyTypes'] = body_types
                    similar_product_data['heights'] = heights
                    
                    # Проверяем дубликаты по названию и бренду
                    product_name = similar_product_data.get('name', '').strip()
                    product_brand = similar_product_data.get('brand', '').strip()
                    
                    if product_name and product_brand:
                        # Проверяем в коллекции products_enhanced
                        duplicate_in_enhanced = mongo_config.collection_enhanced.find_one({
                            'name': product_name,
                            'brand': product_brand
                        })
                        if duplicate_in_enhanced:
                            print(f"   ⚠️ Дубликат по названию и бренду в products_enhanced:")
                            print(f"      Название: {product_name}")
                            print(f"      Бренд: {product_brand}")
                            print(f"      Существующий URL: {duplicate_in_enhanced.get('url', 'N/A')}")
                            skipped_duplicates += 1
                            continue
                    
                    # Добавляем товар в коллекцию products_enhanced
                    result = mongo_config.collection_enhanced.insert_one(similar_product_data)
                    
                    if result.inserted_id:
                        print(f"   ✅ Похожий товар успешно добавлен в базу данных")
                        print(f"      Название: {similar_product_data['name']}")
                        print(f"      Бренд: {similar_product_data['brand']}")
                        print(f"      Цена: {similar_product_data['price']} ₽")
                        print(f"      Категория: {similar_product_data['category']}")
                        print(f"      Подкатегория: {similar_product_data['subcategory']}")
                        print(f"      Изображение: {similar_product_data['imageUrl']}")
                        print(f"      Цветотипы: {color_types}")
                        print(f"      Типы Киббе: {kibbe_types}")
                        print(f"      Типы телосложения: {body_types}")
                        print(f"      Росты: {heights}")
                        added_count += 1
                    else:
                        print(f"   ❌ Ошибка добавления товара в базу данных: {similar_url}")
                    
                    # Пауза между товарами
                    if i < len(similar_urls):
                        pause = random.uniform(2, 4)
                        print(f"   ⏸️ Пауза {pause:.1f}с перед следующим товаром...")
                        await asyncio.sleep(pause)
                    
                except Exception as e:
                    print(f"   ❌ Ошибка обработки похожего товара {i}: {e}")
                    skipped_errors += 1
                    continue
            
            print(f"\n📊 Результат обработки исходного товара:")
            print(f"   Обработано похожих товаров: {len(similar_urls)}")
            print(f"   ✅ Добавлено новых товаров: {added_count}")
            print(f"   ⚠️ Пропущено дубликатов: {skipped_duplicates}")
            print(f"   ❌ Пропущено ошибок: {skipped_errors}")
            print(f"   📈 Эффективность: {(added_count / len(similar_urls) * 100):.1f}%")
            
            return added_count
            
        except Exception as e:
            print(f"❌ Ошибка обработки исходного товара: {e}")
            return 0

    async def close(self):
        """Закрывает соединения"""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            print("✅ Браузер закрыт")
        except Exception as e:
            print(f"⚠️ Ошибка закрытия браузера: {e}")

async def main():
    """Запускает улучшенный парсер визуально похожих товаров"""
    print("🚀 Запуск улучшенного парсера визуально похожих товаров...")
    
    # Создаем парсер
    parser = EnhancedSimilarParser()
    
    if await parser.start_browser():
        try:
            # Подключаемся к MongoDB
            mongo_config.connect()
            
            # Создаем коллекцию products_enhanced если её нет
            if not hasattr(mongo_config, 'collection_enhanced'):
                mongo_config.collection_enhanced = mongo_config.db['products_enhanced']
                print("✅ Коллекция products_enhanced создана")
            
            # Тестовый URL
            test_url = "https://lamoda.ru/p/mp002xw1fli9/clothes-sela-rubashka-dzhinsovaya/"
            
            # Обрабатываем один товар
            await parser.process_source_product(test_url)
            
        finally:
            await parser.close()
    else:
        print("❌ Не удалось подключиться к браузеру")

if __name__ == "__main__":
    asyncio.run(main()) 
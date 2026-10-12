# Кампания и испытания

Кампания состоит из пяти глав по три уровня. Следующий уровень вводит новое решение: экономику, замедление, взрыв, пробивание брони или совмещение этих приёмов. Испытания доступны отдельно и меняют правила, а не только случайное зерно.

## Кампания

- [Первый росток](campaign-01-first-sprout.md)
- [Солнечный урожай](campaign-02-sun-harvest.md)
- [Крепкий орех](campaign-03-stone-barrier.md)
- [Холодные следы](campaign-04-cold-tracks.md)
- [Оттепель на флангах](campaign-05-thaw-crossing.md)
- [Белый шквал](campaign-06-white-storm.md)
- [Школа подрывника](campaign-07-fuse-school.md)
- [Вишнёвый перекрёсток](campaign-08-cherry-crossroads.md)
- [Сапёрный лимит](campaign-09-fixed-budget.md)
- [Двойной ствол](campaign-10-double-barrel.md)
- [Щитолом](campaign-11-shield-breaker.md)
- [Плодородная земля](campaign-12-rich-soil.md)
- [Долгая вахта](campaign-13-long-watch.md)
- [Два горизонта](campaign-14-split-horizon.md)
- [Последний звонок](campaign-15-last-bell.md)

## Испытания

- [Последняя монета](challenge-01-last-coin.md)
- [Живой сад](challenge-02-living-orchard.md)
- [Стеклянная батарея](challenge-03-glass-cannon.md)
- [Ореховый лабиринт](challenge-04-wall-garden.md)
- [Пять стрелков](challenge-05-five-shooters.md)
- [Сухая зима](challenge-06-dry-winter.md)
- [Взрывной конвейер](challenge-07-demolition-derby.md)
- [Три воротца](challenge-08-three-gates.md)
- [Беговой патруль](challenge-09-runner-patrol.md)
- [До звонка](challenge-10-overtime.md)

Все появления заданы расписанием. Одинаковый уровень воспроизводится одинаково при любом поддерживаемом размере тика. Нумерация рядов в инструкциях начинается с 1, в данных — с 0.

## Продвинутые испытания

- [Минное поле](challenge-11-minefield.md)
- [Вишнёвый маршрут](challenge-12-cherry-tour.md)
- [Голодная пятёрка](challenge-13-hungry-five.md)
- [Сапёрная батарея](challenge-14-sapper-battery.md)
- [Дорогие грядки](challenge-15-premium-garden.md)
- [Передовая грядка](challenge-16-forward-line.md)
- [Солнце по расписанию](challenge-17-wave-payday.md)
- [Малое хранилище](challenge-18-small-vault.md)
- [Одна вишня](challenge-19-one-cherry.md)
- [Точка опоры](challenge-20-nut-position.md)
- [Дорогая весна](challenge-21-price-rise.md)
- [Два темпа](challenge-22-two-speeds.md)
- [Кусающийся тыл](challenge-23-biting-rear.md)
- [Широкий фронт](challenge-24-wide-blast.md)
- [Ледяной резерв](challenge-25-frost-reserve.md)
- [Прижать к стене](challenge-26-pin-to-wall.md)
- [Очередь по бегунам](challenge-27-burst-drill.md)
- [Малые партии](challenge-28-small-batches.md)
- [Вишневая касса](challenge-29-cherry-register.md)
- [Сменяющийся дозор](challenge-30-changing-watch.md)

## Проверка проходимости

Для каждого уровня сохранён проверочный маршрут посадок в `solutions/`. Это открытые примеры решения на обычной сложности, а не обязательный способ игры. Тест воспроизводит только разрешённые посадки через тот же API, что используется при нажатии пробела, и требует победу, уничтожение всех запланированных врагов и сохранение всех газонокосилок. Маршруты проверяются с игровым тиком 50, 100, 200 и 500 мс.

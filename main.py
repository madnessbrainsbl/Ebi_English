#!/usr/bin/env python3
"""
Ebi_English — адаптивное изучение английского по карточкам.
Алгоритм SM-2: чем чаще ошибаешься — тем чаще карточка повторяется.
"""

import json
import os
import sys
import time
import random
import datetime
import math
import tempfile

# ───────────────────────── пути к файлам ──────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
VOCAB_FILE  = os.path.join(BASE_DIR, "vocabulary.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "progress.json")
LOG_FILE    = os.path.join(BASE_DIR, "mistakes.log")

# ───────────────────────── цвета (ANSI) ───────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"
    WHITE  = "\033[97m"

def color(text, *codes):
    return "".join(codes) + text + C.RESET

def clear():
    os.system("cls" if os.name == "nt" else "clear")

# ───────────────────────── логирование ────────────────────────────
def log_mistake(card, user_answer, correct_answer, session_score):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = (f"[{ts}] ОШИБКА | EN: {card['en']:20s} | RU: {card['ru']:25s} "
            f"| Ответ пользователя: '{user_answer}' | "
            f"Счёт сессии: {session_score['correct']}/{session_score['correct']+session_score['wrong']}\n")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

def log_session(stats):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = stats['correct'] + stats['wrong']
    pct = int(stats['correct'] / total * 100) if total else 0
    line = (f"[{ts}] СЕССИЯ | Правильно: {stats['correct']}/{total} ({pct}%) "
            f"| Карточек повторено: {stats['reviewed']} "
            f"| Новых слов: {stats['new_cards']}\n")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)

# ──────────────────── хранение прогресса (SM-2) ───────────────────
def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                progress = json.load(f)
            if not isinstance(progress, dict) or not isinstance(progress.get("cards"), dict):
                raise ValueError("неверная структура карточек")
            levels = progress.get("unlocked_levels")
            if not isinstance(levels, list) or not levels or any(
                not isinstance(level, str) or not level.isdigit() for level in levels
            ):
                raise ValueError("неверный список уровней")
            for key in ("total_sessions", "total_correct", "total_wrong"):
                value = progress.get(key)
                if type(value) is not int or value < 0:
                    raise ValueError(f"неверный счётчик {key}")
            for card in progress["cards"].values():
                if not isinstance(card, dict):
                    raise ValueError("неверная карточка прогресса")
                for key in ("interval", "repetitions", "correct", "wrong"):
                    if type(card.get(key)) is not int or card[key] < 0:
                        raise ValueError(f"неверный счётчик карточки {key}")
                for key in ("easiness", "due", "last_seen"):
                    if type(card.get(key)) not in (int, float) or not math.isfinite(card[key]) or card[key] < 0:
                        raise ValueError(f"неверное значение карточки {key}")
            return progress
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Файл прогресса повреждён: {PROGRESS_FILE}. Исходный файл сохранён. {error}") from error
    return {"cards": {}, "unlocked_levels": ["1"], "total_sessions": 0,
            "total_correct": 0, "total_wrong": 0}

def save_progress(progress):
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=os.path.dirname(PROGRESS_FILE),
            prefix=".progress-", suffix=".tmp", delete=False,
        ) as f:
            temporary_path = f.name
            json.dump(progress, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, PROGRESS_FILE)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)

def get_card_data(progress, card_id):
    """Возвращает SM-2 данные карточки (создаёт если нет)."""
    if card_id not in progress["cards"]:
        progress["cards"][card_id] = {
            "easiness": 2.5,   # коэффициент лёгкости (SM-2)
            "interval": 1,     # дней до следующего повторения
            "repetitions": 0,  # сколько раз правильно подряд
            "due": 0,          # timestamp следующего повторения
            "correct": 0,
            "wrong": 0,
            "last_seen": 0
        }
    return progress["cards"][card_id]

def update_sm2(card_data, quality):
    """
    Обновляет SM-2 параметры.
    quality: 0=полный провал, 1=неверно, 2=с трудом, 3=нормально, 4=хорошо, 5=идеально
    """
    now = time.time()
    if quality >= 3:
        if card_data["repetitions"] == 0:
            card_data["interval"] = 1
        elif card_data["repetitions"] == 1:
            card_data["interval"] = 6
        else:
            card_data["interval"] = math.ceil(card_data["interval"] * card_data["easiness"])
        card_data["repetitions"] += 1
        card_data["due"] = now + card_data["interval"] * 86400
    else:
        card_data["repetitions"] = 0
        card_data["interval"] = 1
        card_data["due"] = now

    card_data["easiness"] = max(
        1.3,
        card_data["easiness"] + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    )
    card_data["last_seen"] = now

def is_due(card_data):
    return time.time() >= card_data["due"]

# ──────────────────── загрузка словаря ────────────────────────────
def load_vocabulary():
    with open(VOCAB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_all_cards(vocab, progress):
    """Возвращает список карточек доступных уровней."""
    cards = []
    for lvl in progress["unlocked_levels"]:
        if lvl in vocab["levels"]:
            for card in vocab["levels"][lvl]["cards"]:
                card_id = f"{lvl}_{card['en']}"
                cards.append((card_id, card, lvl))
    return cards

def cards_to_review(all_cards, progress):
    """Карточки просроченные (due) или новые."""
    due, new = [], []
    for card_id, card, lvl in all_cards:
        if card_id in progress["cards"]:
            if is_due(progress["cards"][card_id]):
                due.append((card_id, card, lvl))
        else:
            new.append((card_id, card, lvl))
    return due, new

# ──────────────────── UI-хелперы ──────────────────────────────────
def print_header():
    clear()
    print(color("╔══════════════════════════════════════════╗", C.CYAN, C.BOLD))
    print(color("║          Ebi_English — с нуля           ║", C.CYAN, C.BOLD))
    print(color("╚══════════════════════════════════════════╝", C.CYAN, C.BOLD))
    print()

def print_progress_bar(value, max_value, width=30, label=""):
    filled = int(width * value / max_value) if max_value else 0
    bar = "█" * filled + "░" * (width - filled)
    pct = int(value / max_value * 100) if max_value else 0
    print(f"  {label} [{color(bar, C.GREEN)}] {pct}%")

def ask(prompt, hint=""):
    if hint:
        print(color(f"  ({hint})", C.GRAY))
    try:
        return input(color(f"  {prompt}: ", C.YELLOW)).strip()
    except (KeyboardInterrupt, EOFError):
        return "q"

def normalize(s):
    """Нормализует ответ для сравнения."""
    return s.lower().strip().replace("ё", "е")

def check_answer(user, correct):
    """Нечёткая проверка: разрешает небольшие опечатки."""
    u = normalize(user)
    # Если правильных вариантов несколько (через /)
    variants = [normalize(v.strip()) for v in correct.split("/")]
    if u in variants:
        return True
    # Допускаем 1 ошибку в словах длиннее 4 букв
    for v in variants:
        if len(v) > 4 and levenshtein(u, v) == 1:
            return True
    return False

def levenshtein(a, b):
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i-1] == b[j-1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n]

# ──────────────────── режимы карточек ─────────────────────────────
def quiz_en_to_ru(card):
    """Показывает английское слово — нужно написать по-русски."""
    print(color(f"\n  {'EN →':6}", C.GRAY), color(card["en"], C.WHITE, C.BOLD))
    print(color(f"  Пример: {card['example']}", C.GRAY))
    print()
    return ask("Перевод на русский")

def quiz_ru_to_en(card):
    """Показывает русское слово — нужно написать по-английски."""
    print(color(f"\n  {'RU →':6}", C.GRAY), color(card["ru"], C.WHITE, C.BOLD))
    print()
    return ask("Перевод на английский")

def quiz_choice(card, all_cards_pool):
    """4 варианта ответа — выбери правильный."""
    wrong_pool = [c for _, c, _ in all_cards_pool if normalize(c["ru"]) != normalize(card["ru"])]
    if len(wrong_pool) < 3:
        return quiz_en_to_ru(card)
    wrong = random.sample(wrong_pool, 3)
    options = [card["ru"]] + [w["ru"] for w in wrong]
    random.shuffle(options)
    correct_idx = options.index(card["ru"]) + 1

    print(color(f"\n  {'EN →':6}", C.GRAY), color(card["en"], C.WHITE, C.BOLD))
    print(color(f"  Пример: {card['example']}", C.GRAY))
    print()
    for i, opt in enumerate(options, 1):
        print(f"   {color(str(i)+'.', C.CYAN)} {opt}")
    print()
    ans = ask("Введи номер (1-4)")
    if ans == str(correct_idx):
        return card["ru"]
    return ans  # вернём неверный ответ

# ──────────────────── основная сессия ─────────────────────────────
def adaptive_delay(card_data):
    """Чем хуже результат — тем меньше карточек за раз."""
    wrong = card_data.get("wrong", 0)
    correct = card_data.get("correct", 0)
    if wrong > correct * 2 and wrong > 2:
        return True  # эта карточка "сложная"
    return False

def run_session(progress, vocab):
    all_cards = get_all_cards(vocab, progress)
    due_cards, new_cards = cards_to_review(all_cards, progress)

    # Адаптация: если в прогрессе много ошибок — ограничиваем новые слова
    total_wrong = progress.get("total_wrong", 0)
    total_correct = progress.get("total_correct", 0)
    total = total_correct + total_wrong
    accuracy = total_correct / total if total > 0 else 1.0

    if accuracy < 0.5 and total > 10:
        new_limit = 2   # слабый результат — мало новых слов
    elif accuracy < 0.7 and total > 10:
        new_limit = 5
    else:
        new_limit = 10  # норма

    session_cards = due_cards + new_cards[:new_limit]
    random.shuffle(session_cards)

    if not session_cards:
        print(color("\n  Отличная работа! Нет карточек для повторения.", C.GREEN, C.BOLD))
        print(color("  Возвращайся позже — SM-2 рассчитает когда повторить.", C.GRAY))
        return

    session_stats = {"correct": 0, "wrong": 0, "reviewed": 0, "new_cards": len(new_cards[:new_limit])}

    # Определяем режим — у новичков только выбор, потом постепенно усложняем
    use_choice_mode = accuracy < 0.6 or total < 20

    print(color(f"\n  Сессия: {len(session_cards)} карточек", C.CYAN))
    if accuracy < 0.6 and total > 5:
        print(color("  [Адаптация] Ты часто ошибаешься — переключаюсь в режим выбора из 4.", C.YELLOW))
    print(color("  Введи 'q' для выхода в любой момент.\n", C.GRAY))
    time.sleep(1)

    hard_cards = []  # карточки для повторного прохода
    quit_requested = False

    for card_id, card, lvl in session_cards:
        card_data = get_card_data(progress, card_id)
        is_hard = adaptive_delay(card_data)

        clear()
        print_header()
        done = session_stats['correct'] + session_stats['wrong']
        total_s = len(session_cards)
        print_progress_bar(done, total_s, label=f"Прогресс сессии")
        print(color(f"\n  Уровень: {lvl} — {vocab['levels'][lvl]['name']}", C.GRAY))
        if is_hard:
            print(color("  Сложная карточка — повторяется чаще!", C.YELLOW))

        # Выбираем режим вопроса
        mode_roll = random.random()
        if use_choice_mode or is_hard:
            user_ans = quiz_choice(card, all_cards)
            correct_val = card["ru"]
        elif mode_roll < 0.5:
            user_ans = quiz_en_to_ru(card)
            correct_val = card["ru"]
        else:
            user_ans = quiz_ru_to_en(card)
            correct_val = card["en"]

        if user_ans.lower() == "q":
            quit_requested = True
            break

        if check_answer(user_ans, correct_val):
            print(color("\n  Правильно!", C.GREEN, C.BOLD))
            quality = 5 if card_data["repetitions"] > 1 else 4
            card_data["correct"] += 1
            session_stats["correct"] += 1
            progress["total_correct"] += 1
        else:
            print(color(f"\n  Неверно.", C.RED, C.BOLD))
            print(color(f"  Правильный ответ: {correct_val}", C.YELLOW))
            quality = 1
            card_data["wrong"] += 1
            session_stats["wrong"] += 1
            progress["total_wrong"] += 1
            log_mistake(card, user_ans, correct_val, session_stats)
            hard_cards.append((card_id, card, lvl))

        update_sm2(card_data, quality)
        session_stats["reviewed"] += 1
        save_progress(progress)
        time.sleep(1.5)

    # Повторный проход по ошибкам (если есть)
    if not quit_requested and hard_cards and session_stats["wrong"] > 0:
        print(color(f"\n  Повторяем {len(hard_cards)} карточек с ошибками...", C.YELLOW, C.BOLD))
        time.sleep(1.5)
        for card_id, card, lvl in hard_cards:
            card_data = get_card_data(progress, card_id)
            clear()
            print_header()
            print(color("\n  ПОВТОРЕНИЕ ОШИБОК", C.RED, C.BOLD))
            user_ans = quiz_en_to_ru(card)
            if user_ans.lower() == "q":
                break
            if check_answer(user_ans, card["ru"]):
                print(color("\n  Теперь правильно!", C.GREEN, C.BOLD))
                session_stats["correct"] += 1
                progress["total_correct"] += 1
                card_data["correct"] += 1
                update_sm2(card_data, 3)
            else:
                print(color(f"\n  Снова неверно. Ответ: {card['ru']}", C.RED))
                session_stats["wrong"] += 1
                progress["total_wrong"] += 1
                card_data["wrong"] += 1
                log_mistake(card, user_ans, card["ru"], session_stats)
                update_sm2(card_data, 0)
            session_stats["reviewed"] += 1
            save_progress(progress)
            time.sleep(1.5)

    if not session_stats["reviewed"]:
        return

    # Проверка разблокировки нового уровня
    check_unlock(progress, vocab)

    log_session(session_stats)
    progress["total_sessions"] += 1
    save_progress(progress)
    show_session_results(session_stats, progress)

def check_unlock(progress, vocab):
    """Разблокирует новый уровень если текущие изучены достаточно хорошо."""
    total_correct = progress.get("total_correct", 0)
    total_wrong = progress.get("total_wrong", 0)
    total = total_correct + total_wrong
    accuracy = total_correct / total if total > 0 else 0

    current_max = max(int(l) for l in progress["unlocked_levels"])
    next_level = str(current_max + 1)

    if next_level in vocab["levels"]:
        cards_in_current = sum(
            len(vocab["levels"][l]["cards"])
            for l in progress["unlocked_levels"]
            if l in vocab["levels"]
        )
        learned = sum(
            1 for cid, cd in progress["cards"].items()
            if cd["repetitions"] >= 2 and cd["correct"] > cd["wrong"]
        )
        if learned >= max(3, cards_in_current // 2) and accuracy >= 0.6:
            progress["unlocked_levels"].append(next_level)
            lvl_name = vocab["levels"][next_level]["name"]
            print(color(f"\n  Разблокирован новый уровень: {next_level} — {lvl_name}!", C.GREEN, C.BOLD))
            time.sleep(2)

def show_session_results(stats, progress):
    clear()
    print_header()
    total = stats['correct'] + stats['wrong']
    pct = int(stats['correct'] / total * 100) if total else 0

    print(color("  РЕЗУЛЬТАТЫ СЕССИИ", C.CYAN, C.BOLD))
    print()
    print(f"  Правильно:  {color(str(stats['correct']), C.GREEN)}  /  {total}")
    print(f"  Ошибки:     {color(str(stats['wrong']), C.RED)}")
    print(f"  Точность:   {color(str(pct)+'%', C.YELLOW, C.BOLD)}")
    print(f"  Новых слов: {color(str(stats['new_cards']), C.CYAN)}")
    print()

    global_total = progress['total_correct'] + progress['total_wrong']
    global_pct = int(progress['total_correct'] / global_total * 100) if global_total else 0
    print(color(f"  Всего за всё время: {progress['total_correct']}/{global_total} ({global_pct}%)", C.GRAY))
    print(color(f"  Сессий пройдено: {progress['total_sessions']}", C.GRAY))
    print()

    if pct >= 90:
        print(color("  Превосходно! Так держать!", C.GREEN, C.BOLD))
    elif pct >= 70:
        print(color("  Хорошая работа! Продолжай.", C.YELLOW, C.BOLD))
    elif pct >= 50:
        print(color("  Неплохо, но есть куда расти.", C.YELLOW))
    else:
        print(color("  Много ошибок — не сдавайся! Повтори сложные слова.", C.RED))

    input(color("\n  Нажми Enter для продолжения...", C.GRAY))

# ──────────────────── просмотр статистики ─────────────────────────
def show_stats(progress, vocab):
    clear()
    print_header()
    print(color("  СТАТИСТИКА", C.CYAN, C.BOLD))
    print()

    total = progress['total_correct'] + progress['total_wrong']
    pct = int(progress['total_correct'] / total * 100) if total else 0

    print(f"  Сессий:          {color(str(progress['total_sessions']), C.WHITE, C.BOLD)}")
    print(f"  Всего ответов:   {total}")
    print(f"  Правильно:       {color(str(progress['total_correct']), C.GREEN)}")
    print(f"  Ошибок:          {color(str(progress['total_wrong']), C.RED)}")
    print(f"  Точность:        {color(str(pct)+'%', C.YELLOW, C.BOLD)}")
    print()

    print(color("  Уровни:", C.CYAN))
    for lvl_id, lvl_data in vocab["levels"].items():
        unlocked = lvl_id in progress["unlocked_levels"]
        cards = lvl_data["cards"]
        learned = sum(
            1 for c in cards
            if f"{lvl_id}_{c['en']}" in progress["cards"]
            and progress["cards"][f"{lvl_id}_{c['en']}"]["repetitions"] >= 2
        )
        status = color("открыто", C.GREEN) if unlocked else color("закрыто", C.GRAY)
        bar_len = 20
        filled = int(bar_len * learned / len(cards)) if cards else 0
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  {status} Ур.{lvl_id}: {lvl_data['name'][:25]:25s} [{color(bar, C.BLUE)}] {learned}/{len(cards)}")

    print()
    print(color("  Сложные карточки (>2 ошибок):", C.RED))
    hard = [
        (cid, cd) for cid, cd in progress["cards"].items()
        if cd["wrong"] > 2 and cd["wrong"] > cd["correct"]
    ]
    if hard:
        for cid, cd in sorted(hard, key=lambda x: -x[1]["wrong"])[:5]:
            parts = cid.split("_", 1)
            print(f"    {color(parts[1], C.WHITE)}: ошибок {color(str(cd['wrong']), C.RED)}, правильно {color(str(cd['correct']), C.GREEN)}")
    else:
        print(color("    Пока нет — отлично!", C.GREEN))

    print()
    input(color("  Нажми Enter для возврата...", C.GRAY))

# ──────────────────── просмотр лога ───────────────────────────────
def show_log():
    clear()
    print_header()
    print(color("  ЖУРНАЛ ОШИБОК", C.RED, C.BOLD))
    print()
    if not os.path.exists(LOG_FILE):
        print(color("  Лог пустой — ошибок не было!", C.GREEN))
    else:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        mistakes = [l for l in lines if "ОШИБКА" in l]
        sessions = [l for l in lines if "СЕССИЯ" in l]
        print(color(f"  Всего ошибок в журнале: {len(mistakes)}", C.YELLOW))
        print(color(f"  Всего сессий в журнале: {len(sessions)}", C.CYAN))
        print()
        print(color("  Последние 10 ошибок:", C.RED))
        for line in mistakes[-10:]:
            # Вырезаем суть
            parts = line.strip().split("|")
            if len(parts) >= 3:
                ts = parts[0].strip()[1:-1]
                en = parts[1].replace("EN:", "").strip()
                ru = parts[2].replace("RU:", "").strip()
                print(f"    {color(ts, C.GRAY)} | {color(en, C.WHITE)} → {color(ru, C.YELLOW)}")
        print()
        print(color("  Последние сессии:", C.CYAN))
        for line in sessions[-5:]:
            print(f"    {color(line.strip(), C.GRAY)}")

    print()
    input(color("  Нажми Enter для возврата...", C.GRAY))

# ──────────────────── просмотр всех слов ──────────────────────────
def browse_cards(vocab, progress):
    clear()
    print_header()
    print(color("  СЛОВАРЬ", C.CYAN, C.BOLD))
    print()
    for lvl_id, lvl_data in vocab["levels"].items():
        unlocked = lvl_id in progress["unlocked_levels"]
        status = color("открыто", C.GREEN) if unlocked else color("закрыто", C.GRAY)
        print(color(f"\n  {status} Уровень {lvl_id}: {lvl_data['name']}", C.CYAN, C.BOLD))
        if unlocked:
            for card in lvl_data["cards"]:
                cid = f"{lvl_id}_{card['en']}"
                cd = progress["cards"].get(cid, {})
                reps = cd.get("repetitions", 0)
                star = color("выучено", C.YELLOW) if reps >= 2 else color("в работе", C.GRAY)
                print(f"    {star} {color(card['en'], C.WHITE):20s} — {card['ru']}")
        else:
            print(color("    (закрыт — изучи предыдущий уровень)", C.GRAY))

    print()
    input(color("  Нажми Enter для возврата...", C.GRAY))

# ──────────────────── главное меню ────────────────────────────────
def main_menu(progress, vocab):
    while True:
        clear()
        print_header()

        all_cards = get_all_cards(vocab, progress)
        due, new = cards_to_review(all_cards, progress)
        total_due = len(due) + min(len(new), 10)

        total = progress['total_correct'] + progress['total_wrong']
        pct = int(progress['total_correct'] / total * 100) if total > 0 else 0

        print(color(f"  Разблокировано уровней: {len(progress['unlocked_levels'])}/{len(vocab['levels'])}", C.GRAY))
        print(color(f"  Общая точность: {pct}%  |  Сессий: {progress['total_sessions']}", C.GRAY))
        print()

        if total_due > 0:
            print(color(f"  [{total_due} карточек ждут повторения]", C.YELLOW))
        else:
            print(color("  [Все карточки повторены — заходи позже!]", C.GREEN))
        print()

        print(color("  1.", C.CYAN), "Начать сессию")
        print(color("  2.", C.CYAN), "Статистика")
        print(color("  3.", C.CYAN), "Словарь (все слова)")
        print(color("  4.", C.CYAN), "Журнал ошибок")
        print(color("  q.", C.GRAY), "Выход")
        print()

        choice = ask("Выбери").lower()

        if choice == "1":
            run_session(progress, vocab)
        elif choice == "2":
            show_stats(progress, vocab)
        elif choice == "3":
            browse_cards(vocab, progress)
        elif choice == "4":
            show_log()
        elif choice == "q":
            print(color("\n  До встречи! Keep learning!\n", C.CYAN, C.BOLD))
            break

# ──────────────────── точка входа ─────────────────────────────────
def main():
    # Включаем ANSI в Windows
    if os.name == "nt":
        os.system("color")
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass

    if not os.path.exists(VOCAB_FILE):
        print("Файл vocabulary.json не найден рядом с main.py!")
        sys.exit(1)

    progress = None
    try:
        vocab = load_vocabulary()
        progress = load_progress()
        main_menu(progress, vocab)
    except (OSError, ValueError) as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        if progress is not None:
            save_progress(progress)

if __name__ == "__main__":
    main()

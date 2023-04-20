from telebot.async_telebot import AsyncTeleBot
from telebot import types
from time import time, sleep
from MCP3008 import MCP3008
from serial import Serial
from pynmea2 import parse as gpsParse
import asyncio

bot = AsyncTeleBot("TOKEN")
gps = Serial("/dev/serial0", baudrate=9600, timeout=0.5)
adc = MCP3008()
locMsg = []
cal = [99999, 0]


def checkCalibration(lst, calOffset):
    sr = sum(lst) / len(lst)
    for num in lst:
        if not (sr - calOffset < num < sr + calOffset):
            return False
    return True

#координаты с датчика
async def getLoc():
    global gps
    data = ""
    for rep in range(1, 6):
        cRep = 1
        while data[:6] != "$GPGGA":
            try:
                data = gps.readline().decode()
            except:
                print(
                    f"\033[33mretrying to fetch location from GPS sensor, attempt {cRep} (can't connect to sensor)\033[37m")
                if cRep == 5:
                    print("\033[31mfailed to fetch location from GPS sensor (can't connect to sensor)\033[37m")
                    return False, False
                cRep += 1
                await asyncio.sleep(0.5)
            if data == "":
                print(
                    f"\033[33mretrying to fetch location from GPS sensor, attempt {cRep} (can't connect to sensor)\033[37m")
                if cRep == 5:
                    print("\033[31mfailed to fetch location from GPS sensor (can't connect to sensor)\033[37m")
                    return False, False
                cRep += 1
                await asyncio.sleep(0.5)
        fData = gpsParse(data)
        if fData.latitude == 0 or fData.longitude == 0: #latitude(широта) longitude(долгота)
            print(
                f"\033[33mretrying to fetch location from GPS sensor, attempt {rep} (can't fetch location data)\033[37m")
            await asyncio.sleep(0.5)
            continue
        return fData.latitude, fData.longitude
    print("\033[31mfailed to fetch location from GPS sensor (can't fetch location data)\033[37m")
    return False, False


async def updateGeo():
    global locMsg, bot
    while True:
        lat, lon = await getLoc()
        locMsg1 = list(locMsg)
        for msg in locMsg1:
            if not lat or not lon:
                print("\033[31mfailed to edit location\033[37m")
                break
            if msg[0] + 3600 > int(time()):  # один час обновления
                try:
                    await bot.edit_message_live_location(lat, lon, chat_id=msg[1], message_id=msg[2])
                    print(f"\033[32mupdated location for {msg[1]}\033[37m")
                except Exception as e:
                    if not "same" in str(e):
                        locMsg.remove(msg) #если сообщение с геолокацией дублируется, то старое удаляется
                        print(f"\033[32mremoved location update for {msg[1]} (second location from same user)\033[37m")
                    else:
                        pass
            else:
                locMsg.remove(msg)
                print(f"\033[32mremoved location update for {msg[1]} (timeout)\033[37m")
        await asyncio.sleep(30)  # update every 30 seconds


def termo():
    global adc, sr
    return round(((adc.read() - sr) / 1024) * 100) if round((adc.read() - sr)) > 0 else 0


@bot.message_handler(commands=['start'])
async def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Метан")
    btn2 = types.KeyboardButton("Координата")
    markup.add(btn1, btn2)
    await bot.send_message(message.chat.id,
                           text="Я чат-бот дрона с датчиком метана.\n\nКоманды, которые я могу выполнять: \n   определить количество метана в воздухе (Метан)\n   сказать координату расположения дрона (Координата)",
                           reply_markup=markup)


@bot.message_handler(content_types=['text'])
async def func(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Метан")
    btn2 = types.KeyboardButton("Координата")
    markup.add(btn1, btn2)
    global locMsg
    if (message.text == "Метан"):
        await bot.send_message(message.chat.id, text=f"Значение с датчика газа: {termo()}%", reply_markup=markup)
        print("\033[32mgot gas sensor values\033[37m")

    elif (message.text == "Координата"):
        lat, lon = await getLoc() #ширина, долгота
        if not lat or not lon:
            await bot.send_message(message.chat.id,
                                   text="Не получилось получить значения с GPS датчика, попробуйте позже")
            print("\033[31mfailed to send location\033[37m")
        else:
            geoMessage = await bot.send_location(message.chat.id, lat, lon, live_period=3600)
            await bot.send_message(message.chat.id, text="Геопозиция дрона", reply_markup=markup)
            print("\033[32mgot GPS sensor values\033[37m")
            locMsg.append([int(time()), geoMessage.chat.id, geoMessage.message_id])

    else:
        await bot.send_message(message.chat.id, text="Я не знаю таких команд...", reply_markup=markup)


if __name__ == "__main__":
    print("\033[32mheating and calibrating gas sensor\033[37m")
    while not checkCalibration(cal, 5):
        cal = []
        for _ in range(10):
            cal.append(adc.read())
            sleep(0.1)
    sr = round(sum(cal) / len(cal))
    print(f"\033[32mgas sensor heated and calibrated (calibration value: {sr})\033[37m")
    loop = asyncio.get_event_loop() #пул функции
    loop.create_task(bot.polling(), name="bot") #функция телеграм-бота
    loop.create_task(updateGeo(), name="update geo") #функция обновления геолокации
    loop.run_forever() #навсегда крутит задания

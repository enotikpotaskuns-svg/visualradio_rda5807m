#!/bin/bash

# Останавливать скрипт при любой ошибке
set -e

echo "=== НАЧАЛО АВТОМАТИЧЕСКОЙ УСТАНОВКИ VISUALRADIO ==="
echo "[ 1/5 ] Установка системных зависимостей и утилит сборки..."
sudo apt update
sudo apt install -y git build-essential linux-headers-$(uname -r) python3-tk python3-pip python3-venv i2c-tools

echo "[ 2/5 ] Скачивание, компиляция и фиксация I2C-драйвера CH341A..."
# Качаем исходники драйвера во временную папку, чтобы не зависеть от структуры репозитория
rm -rf /tmp/ch341-driver
git clone https://github.com/frank-zago/ch341-i2c-spi-gpio
cd /tmp/ch341-i2c-spi-gpio
make

sudo mkdir -p /lib/modules/$(uname -r)/kernel/drivers/i2c/busses/
sudo cp ./ch341-core.ko /lib/modules/$(uname -r)/kernel/drivers/i2c/busses/
sudo cp ./i2c-ch341.ko /lib/modules/$(uname -r)/kernel/drivers/i2c/busses/
sudo depmod -a

# Вносим драйвера в автозагрузку ядра (если их там еще нет)
if ! grep -q "ch341-core" /etc/modules; then
    echo "ch341-core" | sudo tee -a /etc/modules
fi
if ! grep -q "i2c-ch341" /etc/modules; then
    echo "i2c-ch341" | sudo tee -a /etc/modules
fi

# Блокируем конфликтный стандартный Serial-драйвер
echo "blacklist ch341" | sudo tee /etc/modprobe.d/blacklist-ch341.conf

# Прописываем udev-правило для автоподхвата при переподключении USB
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="5512", ACTION=="add", RUN+="/sbin/modprobe i2c-ch341"' | sudo tee /etc/udev/rules.d/99-ch341-i2c.rules
sudo udevadm control --reload-rules && sudo udevadm trigger

# Возвращаемся обратно в папку проекта и чистим за собой временные файлы
cd -
rm -rf /tmp/ch341-driver

echo "[ 3/5 ] Создание изолированного окружения Python..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install smbus2

echo "[ 4/5 ] Создание консольной команды 'visualradio'..."
CURRENT_DIR=$(pwd)
cat << 'INNER_EOF' | sudo tee /usr/local/bin/visualradio
#!/bin/bash
cd '$CURRENT_DIR'
sudo ./venv/bin/python radio_gui.py "$@"
INNER_EOF
sudo chmod +x /usr/local/bin/visualradio

echo "[ 5/5 ] Принудительная перезагрузка модулей..."
sudo rmmod i2c-ch341 ch341-core 2>/dev/null || true
sudo modprobe ch341-core || true
sudo modprobe i2c-ch341 || true

echo "=========================================================="
echo "[ УСПЕХ ] Установка завершена!"
echo "1. ПЕРЕДЁРНИ CH341A."
echo "2. Теперь вы можете запускать радио командой: visualradio"
echo "=========================================================="

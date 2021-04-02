#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>

#define RST_PIN 5
#define SS_PIN 53
#define SERVO_PIN 2

MFRC522 mfrc522(SS_PIN, RST_PIN); // Create MFRC522 instance.

int card_uid[] = {0xFF, 0xFF, 0xFF, 0xFF}; //Change to match NFC card

MFRC522::MIFARE_Key key;

Servo lock;

void setup()
{
    Serial.begin(9600);
    SPI.begin();
    mfrc522.PCD_Init();
    for (byte i = 0; i < 6; i++)
    {
        key.keyByte[i] = 0xFF;
    }
    Serial.print(F("Using key (for A and B):"));
    dump_byte_array(key.keyByte, MFRC522::MF_KEY_SIZE);
    lock.attach(SERVO_PIN);
    lock.write(135);
    delay(400);
    lock.detach();
}

void loop()
{
    if (!mfrc522.PICC_IsNewCardPresent())
    {
        return;
    }
    if (!mfrc522.PICC_ReadCardSerial())
    {
        return;
    }
    Serial.print(F("Card UID:"));
    dump_byte_array(mfrc522.uid.uidByte, mfrc522.uid.size);
    Serial.println("\n");
    Serial.println(check_uid(mfrc522.uid.uidByte, mfrc522.uid.size));
    Serial.println();
    Serial.print(F("PICC type: "));
    MFRC522::PICC_Type piccType = mfrc522.PICC_GetType(mfrc522.uid.sak);
    Serial.println(mfrc522.PICC_GetTypeName(piccType));
    delay(3000);
}

void dump_byte_array(byte *buffer, byte bufferSize)
{
    for (byte i = 0; i < bufferSize; i++)
    {
        Serial.print(buffer[i] < 0x10 ? " 0" : " ");
        Serial.print(buffer[i], HEX);
    }
}

bool check_uid(byte *buffer, byte bufferSize)
{
    int correct = 0;
    for (byte i = 0; i < bufferSize; i++)
    {
        Serial.print(buffer[i]);
        Serial.print(" | ");
        Serial.println(card_uid[i]);
        if (buffer[i] == card_uid[i])
        {
            correct += 1;
        }
    }
    if (correct == 4)
    {
        Serial.println("Access granted");
        lock.attach(SERVO_PIN);
        lock.write(180);
        delay(10000);
        lock.write(135);
        delay(1000);
        lock.detach();
        return true;
    }
}
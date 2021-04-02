char inChar = ' ';

#define START '^'
#define END '$'
#define NOTSET 0
#define UID_LENGTH 16

byte CRC8(const byte *data, byte len)
{
    byte crc = 0x00;
    while (len--)
    {
        byte extract = *data++;
        for (byte tempI = 8; tempI; tempI--)
        {
            byte sum = (crc ^ extract) & 0x01;
            crc >>= 1;
            if (sum)
            {
                crc ^= 0x8C;
            }
            extract >>= 1;
        }
    }
    return crc;
}

enum OPERATION
{
    OP_NOTSET,
    READ,
    WRITE,
    CHECK,
    UID,
};

struct
{
    char UID[UID_LENGTH];
    bool is_present;
    uint16_t time;
} DEVICE;

typedef struct NFCRequest
{
    char target;
    char index;
    char payload[4];
    bool is_success;
} NFCRequest;

void request_start(NFCRequest *request)
{
    request->target = '\0';
    request->index = '\0';
    request->payload[0] = '\0';
    request->is_success = false;
}

typedef void (*op_pointer)(NFCRequest *);

void nfc_read_register(NFCRequest *request)
{
    printf("reading t/i %x/%x", request->target, request->index);
}

void nfc_write_register(NFCRequest *request)
{
    printf("reading t/i/p %x/%x/%x", request->target, request->index, request->payload);
}

void nfc_check_is_present(NFCRequest *request)
{
    printf("nfc_check_is_present %b", request->is_success);
}

void nfc_read_uid(NFCRequest *request)
{
    printf("reading UID %x");
}

op_pointer OPERATIONS[5] = {
    NULL,
    nfc_read_register,
    nfc_write_register,
    nfc_check_is_present,
    nfc_read_uid};

struct
{
    OPERATION op;
    op_pointer op_ptr;
    NFCRequest req;
    bool started;
} PACKET;

void start_packet()
{
    PACKET.op = OP_NOTSET;
    PACKET.op_ptr = NULL;
    request_start(&PACKET.req);
    PACKET.started = true;
}

void finish_packet()
{
    PACKET.op_ptr = OPERATIONS[PACKET.op];
}

void setup()
{
    Serial.begin(2000000);
}

void handle_message()
{
    if (PACKET.op_ptr != NULL)
    {
        PACKET.op_ptr = NULL;
        PACKET.started = false;
        Serial.println("packet finished");
    }
}

void handle_character()
{
    while (Serial.available())
    {
        inChar = (char)Serial.read();
        switch (inChar)
        {
        case START:
            start_packet();
            break;
        case END:
            finish_packet();
            break;
        default:
            break;
        }
    }
    Serial.println("serialEvent() called.");
}

void loop()
{
    handle_message();
}

void serialEvent()
{
    handle_character();
}

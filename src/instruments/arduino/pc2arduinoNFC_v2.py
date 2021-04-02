#Python code to write 128 bytes + header to Arduino w/ NFC tag. 
#Pyserial API here: https://pyserial.readthedocs.io/en/latest/pyserial_api.html

import serial

###############################Object declarations###############################
#to make parsing easier
#reference: http://hlsquare.blogspot.com/2013/11/intel-hex-format.html
class intelHexLine(object):
    startCode = ":"
    byteCount = 0
    addressField = b'\x00\x00'
    recordType = b'\x00'
    data = bytes.fromhex('00')
    checksum = b'\x00'

    def __init__(self, inputString):
        if inputString[0] == ":":
            smallerString = inputString[1:]
            if inputString[-1] == "\n":
                smallerString = smallerString[:-1]
            # self.startCode = ":" #not needed
            self.byteCount = bytes.fromhex(smallerString[:2])[0] #produces an int
            self.addressField = smallerString[2:6] #only ever used when 0x0000
            self.recordType = smallerString[6:8]
            self.data = smallerString[8:-2]
            self.data = [self.data[i:i+2] for i in range(0, len(self.data), 2)] #splits into byte segments
            # if self.recordType == "00":
            #     while len(self.data)<32:
            #         self.data+="F"
            #     self.byteCount = 16
            self.checksum = smallerString[-2:]
        else:
            print("Line parse error: Missing ':'")


#Read through file
packets = [] #will be a 2d list of all the packets to go out
simulatedMemory = ((int('10032fff',16)-int('10001000',16))+1)*["FF"]
lastAddr = "10001000"
# currentPacketBytes = 0
# inputFile = open("simple_bootloader2.hex","r") #read-only
inputFile = open("fakeProgram.hex","r") #read-only
outputFile = open("toRDMController.txt","w+") #write-only, create if not found
writeStartAddress = ""
for line in inputFile:
    currentLine = intelHexLine(line)
    if currentLine.recordType == '04':
        #start address to write to 
        print("Write start address: " + ''.join(currentLine.data))
        writeStartAddress = ''.join(currentLine.data)
    elif currentLine.recordType == '05':
        #address code starts from
        print("Code start address " + ''.join(currentLine.data))
    elif currentLine.recordType == '01':
        print("End of file reached")
        break
    elif currentLine.recordType == '00':
        currentLineBytes = currentLine.data
        currentLineAddress = writeStartAddress + currentLine.addressField
        currentLineIndex = int(currentLineAddress,16) - int("10001000",16)
        for i in range(currentLine.byteCount):
            simulatedMemory[currentLineIndex + i] = currentLine.data[i]
        if int(currentLineAddress,16) > int(lastAddr, 16):
            lastAddr = currentLineAddress
        #Found a data line
        # if currentPacketBytes == 0:
        #     newPacket = [writeStartAddress+currentLine.addressField, currentLine.data]
        #     # newPacket = [currentLine.addressField, currentLine.data]
        #     packets.append(newPacket)
        #     currentPacketBytes += currentLine.byteCount
        # else:
        #     packets[-1][1]+=currentLine.data
        #     currentPacketBytes += currentLine.byteCount
        # if currentPacketBytes >= 128:
        #     currentPacketBytes = 0
    else:
        print("Unsupported recordType: "+currentLine.recordType)


######################memory->packets stuff#######################
#Truncate after last address's page
nextPageIndexAfterLast = ((int(lastAddr,16)-int("10001000",16)+1)//256+1)*256
if not(all([x=="FF" for x in simulatedMemory[nextPageIndexAfterLast:]])):
    print("Adding another page; trying again")
    nextPageIndexAfterLast = ((int(lastAddr,16)-int("10001000",16)+1)//256+2)*256
    if not(all([x=="FF" for x in simulatedMemory[nextPageIndexAfterLast:]])):
        print("Processing error. Check simulatedMemory.")
    else:
        simulatedMemory = simulatedMemory[:nextPageIndexAfterLast]
else:
    simulatedMemory = simulatedMemory[:nextPageIndexAfterLast]
print("lastAddr: " + lastAddr)
#Break into 128 byte chunks. Should be easy as current simulatedMemory length%256=0
print("length simulatedMemory: "+str(len(simulatedMemory)))
offset = int("10007000",16) - int("10001000",16)
for i in range(len(simulatedMemory)//128):
    newPacket = [hex(int("10001000",16)+(i*128)+offset)[2:], ''.join(simulatedMemory[(i*128):((i+1)*128)])]
    packets.append(newPacket)

#File writing for RDM
for packet in packets:
    length = hex(len(bytes.fromhex(packet[1])))[2:]
    if len(length)<2:
        length ="0"+length
    checksum = hex(sum(bytes.fromhex(packet[0]+str(length)+packet[1])))[2:]
    while len(checksum)<4:
        checksum="0"+checksum
    while len(packet[1]) < 128:
        print("should never happen")
    outputFile.write(packet[0] + str(length) + packet[1] + checksum+"\n")
    # print(packet[0] + str(length) + packet[1] + checksum)
    print(packet[0]+" " + str(length)+" " + packet[1] +" " + checksum)

outputFile.write("\n10000000000010\n") #address 0x1000'0000, param data length 0, checksum 10: end of transmission packet
# print(simulatedMemory)

###############################Serial stuff###############################
# ser = serial.Serial( 
#     port="COM7", #change if needed
#     baudrate=9600,
#     bytesize=serial.EIGHTBITS,
#     parity=serial.PARITY_NONE,
#     stopbits=serial.STOPBITS_ONE
#   )
# if(ser.isOpen() == False):
#     ser.open()
# # ser.send_break(0.25) #ex of how to use breaks (0.25 sec in this example)
# arduinoBusy = False
# for packet in packets:
#     ser.write(b'W' + bytes.fromhex(packet[0]) + bytes.fromhex(packet[1]))
#     print(b'W' + bytes.fromhex(packet[0]) + bytes.fromhex(packet[1]))
#     arduinoBusy = True
#     while(arduinoBusy):
#         oneByte = ser.read(1) #checks if there's a byte to read
#         if oneByte == b'R': #Arduino sent back "R", is ready
#             arduinoBusy = False
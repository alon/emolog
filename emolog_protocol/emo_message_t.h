// Emolog protocol enumeration
//
// IMPORTANT
// keep this file as a valid C enum:
// use only double slash comments
// other lines can be whitespaces or contain a valid variable name, an equals
// sign, a number, and finally a comma:
//
// NUM = [0-9]+
// VAR = EMO_MESSAGE_TYPE_[a-zA-Z][0-9a-zA-Z_]*
// LINE = VAR = NUM,
EMO_MESSAGE_TYPE_VERSION = 1,
EMO_MESSAGE_TYPE_PING = 2,
EMO_MESSAGE_TYPE_ACK = 3,
EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE = 4,
EMO_MESSAGE_TYPE_SAMPLER_CLEAR = 5,
EMO_MESSAGE_TYPE_SAMPLER_START = 6,
EMO_MESSAGE_TYPE_SAMPLER_STOP = 7,
EMO_MESSAGE_TYPE_SAMPLER_SAMPLE = 8,

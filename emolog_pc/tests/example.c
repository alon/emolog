int var_int = 10;
float var_float = 20.0;
unsigned char var_unsigned_char = 40;
float var_float8[8] = {0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005};
const float var_float_arr_2[] [2] = {
    { 0.1, 0.2 },
    { 0.2, 0.3 },
    { 0.3, 0.4 },
    { 1.2, 1.3 },
    { 1.3, 1.4 },
};

typedef struct {
    int x;
    float y;
    int z[3];
} S;

S s;

S s_array[3];

int main(void)
{
    float bla = (1000.0) * (var_float8[3] + var_float8[2] + var_float8[1] + var_float8[0] + var_float_arr_2[0][0]);
    return var_int + var_float + var_unsigned_char + bla;
}


// Make gcc-none happy (no _exit symbol error otherwise)
#ifdef __cplusplus
extern "C" {
#endif

void _exit(int status)
{
}

#ifdef __cplusplus
}
#endif


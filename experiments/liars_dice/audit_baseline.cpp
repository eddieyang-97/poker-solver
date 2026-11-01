// Run the archived program unchanged, then export its complete average policy.
// Binary layout: little-endian IEEE float64, mask/type/action (13 padded slots).
#define main archived_main
#include "one_face_cfr.cpp"
#undef main
int main(int argc, char** argv) {
    if (argc != 3 || atoi(argv[1]) <= 0) {
        cerr << "usage: audit_baseline ITERATIONS POLICY.bin\n";
        return 2;
    }
    archived_main(argc, argv);
    ofstream out(argv[2], ios::binary);
    for (int mask=0; mask<M; ++mask) {
        for (int type=0; type<K; ++type) {
            double strategy[A] = {};
            avgStrategy(getPlayer(mask), type, mask, strategy);
            out.write(reinterpret_cast<char*>(strategy), sizeof(strategy));
        }
    }
    return out ? 0 : 1;
}

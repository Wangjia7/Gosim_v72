#include <algorithm>
#include <cmath>
#include <vector>

// Cheap geometry pass: only targets actually on glass need duration/program gains.
extern "C" void classify_field(int n, int side, double glass, double pitch,
    double fov, int gapless, double altitude, double azimuth, const double* xyz,
    const double* margins, int* fibers) {
    constexpr double rad = 3.14159265358979323846 / 180.0;
    const double a=altitude*rad, z=azimuth*rad;
    const double c[3]={std::cos(a)*std::cos(z),std::cos(a)*std::sin(z),std::sin(a)};
    const double north[3]={-std::sin(a)*std::cos(z),-std::sin(a)*std::sin(z),std::cos(a)};
    const double east[3]={-std::sin(z),std::cos(z),0};
    for(int j=0;j<n;++j){
        fibers[j]=-1;
        const double* v=xyz+3*j;
        const double d=v[0]*c[0]+v[1]*c[1]+v[2]*c[2];
        if(d<=0) continue;
        const double y=(v[0]*north[0]+v[1]*north[1]+v[2]*north[2])/d/rad;
        const double x=(v[0]*east[0]+v[1]*east[1]+v[2]*east[2])/d/rad;
        if(std::abs(x)>fov/2 || std::abs(y)>fov/2) continue;
        const int row=std::clamp((int)std::floor(y/pitch+side/2.),0,side-1);
        const int col=std::clamp((int)std::floor(x/pitch+side/2.),0,side-1);
        double margin=glass/2-std::max(std::abs(y-(row-(side-1)/2.)*pitch),std::abs(x-(col-(side-1)/2.)*pitch));
        if(gapless) margin=std::max(0.,margin);
        if(margin>=0 && margin>=margins[j]) fibers[j]=row*side+col;
    }
}

// Evaluate a field for all duration/program pairs. No RNG, threads, subprocesses,
// weather access or clocks: the Python caller budgets process CPU between fields.
extern "C" void evaluate_field(int n, int choices, int side, double glass, double pitch,
    double fov, int gapless, double altitude, double azimuth, const double* xyz,
    const double* margins, const double* gains, int* picks, double* totals) {
    constexpr double rad = 3.14159265358979323846 / 180.0;
    const double a = altitude*rad, z = azimuth*rad;
    const double c[3] = {std::cos(a)*std::cos(z),std::cos(a)*std::sin(z),std::sin(a)};
    const double north[3] = {-std::sin(a)*std::cos(z),-std::sin(a)*std::sin(z),std::cos(a)};
    const double east[3] = {-std::sin(z),std::cos(z),0.0};
    const int fibers=side*side;
    std::fill(picks,picks+choices*fibers,-1);
    std::fill(totals,totals+choices,0.0);
    std::vector<double> best(choices*fibers,0.0);
    for(int j=0;j<n;++j){
        const double* v=xyz+3*j;
        const double d=v[0]*c[0]+v[1]*c[1]+v[2]*c[2];
        if(d<=0.0) continue;
        const double y=(v[0]*north[0]+v[1]*north[1]+v[2]*north[2])/d/rad;
        const double x=(v[0]*east[0]+v[1]*east[1]+v[2]*east[2])/d/rad;
        if(std::abs(x)>fov/2 || std::abs(y)>fov/2) continue;
        const int row=std::clamp((int)std::floor(y/pitch+side/2.0),0,side-1);
        const int col=std::clamp((int)std::floor(x/pitch+side/2.0),0,side-1);
        double margin=glass/2-std::max(std::abs(y-(row-(side-1)/2.0)*pitch),
                                    std::abs(x-(col-(side-1)/2.0)*pitch));
        if(gapless) margin=std::max(0.0,margin);
        if(margin<0.0 || margin<margins[j]) continue;
        const int fiber=row*side+col;
        for(int k=0;k<choices;++k){
            const double g=gains[k*n+j];
            const int at=k*fibers+fiber;
            // Python max((gain,index)) prefers the last equal target in sorted order.
            if(g>0 && (g>best[at] || (g==best[at] && j>picks[at]))){
                best[at]=g; picks[at]=j;
            }
        }
    }
    for(int k=0;k<choices;++k)
        for(int f=0;f<fibers;++f) totals[k]+=best[k*fibers+f];
}

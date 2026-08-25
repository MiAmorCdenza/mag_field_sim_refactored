      SUBROUTINE MAGNETOSHEATH_B (XGSW,YGSW,ZGSW,PSI,PDYN,XMS,BETA,
     * BXIMF_GSW,BYIMF_GSW,BZIMF_GSW,ID,BX,BY,BZ)
c
c  Input:  
c
c   XGSW,YGSW,ZGSW: position in the GSW coord.system
c   PSI:  geodipole tilt in radians
c   PDYN: solar wind ram pressure in nPa
c   XMS:  magnetosonic Mach number
c   BETA: solar wind plasma beta
c   BXIMF_GSW,BYIMF_GSW,BZIMF_GSW: IMF components in GSW coord.system
c
c  Output: 
c
c   ID=0,1,2 means that the point XGSW,YGSW,ZGSW is inside the magnetosheath, 
C            solar wind, and magnetosphere, respectively.
c
c   BX,BY,BZ: magnetosheath magnetic field GSW components 
c              (if ID=2 then zero; if ID=1 then IMF)
c  Note: 
c   XMS and BETA are needed only to define bow shock and magnetopause locations
c   using models by Lu et al.(2019) and Lin et al. (2010), resp.
c                      
      IMPLICIT  REAL * 8  (A - H, O - Z)
C
      DIMENSION A(960),XI(10),F(3),DERX(960),DERY(960),DERZ(960),IA(960)

      DATA A/
     *-322.919D0,106.487D0,488.714D0,-308.314D0,-939.342D0,-505.592D0,
     * 31.3247D0,-10.9180D0,145.172D0,-29.5811D0,217.611D0,-93.6685D0,
     * 7.26498D0,755.022D0,-86.6665D0,-774.208D0,50.4339D0,-287.695D0,
     * 124.601D0,675.546D0,336.163D0,555.209D0,248.219D0,97.9770D0,
     *-145.736D0,79.6398D0,-242.997D0,304.899D0,-255.504D0,-38.5675D0,
     *-355.217D0,32.7292D0,-681.512D0, -34.5063D0,-150.923D0,-12.6718D0,
     *-166.979D0,-35.6272D0,-34.3735D0,-445.107D0, 161.753D0,-58.4308D0,
     * 217.760D0,-255.758D0,-278.138D0, 74.9830D0,-124.474D0, 118.887D0,
     * 56.8235D0,-175.264D0, 78.7691D0,-21.5395D0,-148.999D0, 75.3880D0,
     *-60.1173D0, 744.715D0, 126.209D0, 116.063D0, 60.7747D0,-99.9656D0,
     * 87.9385D0,-93.9355D0,-523.874D0,-70.9629D0,-51.6815D0,-176.190D0,
     *-6.87501D0,0.942380D0,-257.782D0, 411.595D0,-423.952D0,-75.7390D0,
     *-24.3097D0, 74.9005D0, 22.1193D0,-18.5572D0,-177.051D0,-26.5231D0,
     *-20.4844D0,-231.074D0, 88.9250D0, 128.653D0,-176.240D0, 105.172D0,
     * 297.181D0, 88.3627D0, 278.593D0,-153.855D0, 279.497D0,-234.089D0,
     * 18.0243D0, 61.3501D0,-452.198D0,-181.752D0,-48.0398D0,-39.5203D0,
     * 173.155D0,-147.962D0, 167.270D0,-22.4820D0, 35.0863D0, 39.3006D0,
     * 97.3012D0, 26.0693D0, 119.170D0,-35.1365D0,-324.616D0,-119.274D0,
     *-9.08376D0, 24.3680D0,-57.9296D0,-23.3399D0,-32.7627D0, 197.489D0,
     *-57.8974D0,-25.8914D0,-43.2813D0, 30.3267D0,-122.533D0, 280.306D0,
     *-3.46277D0, 25.2094D0,-105.071D0,-27.6590D0,-41.8558D0, 142.148D0,
     *-57.2458D0,-57.0859D0,-73.9216D0,-140.528D0,-149.991D0,-253.539D0,
     *-219.758D0,-12.5608D0,-53.3875D0, 182.643D0, 133.700D0, 18.0663D0,
     * 16.1418D0,-167.802D0, 96.0519D0,-118.907D0, 350.392D0,-2.36812D0,
     *-24.7688D0,-39.7175D0,-23.0364D0, 93.3347D0, 33.4571D0, 131.396D0,
     * 319.728D0, 20.4783D0, 30.5053D0, 19.2217D0, 39.3981D0, 30.2252D0,
     *-148.890D0, 32.6301D0, 46.5338D0, 60.8580D0,-29.7978D0, 47.8021D0,
     *-422.627D0, 24.1744D0,-8.18385D0,-54.5151D0, 3.40985D0,-140.936D0,
     *-45.9849D0, 46.3200D0,-36.3911D0, 18.2120D0, 61.3363D0, 11.3993D0,
     * 6.17439D0, 1.06220D0,-18.2504D0, 4.62393D0,-20.1763D0, 183.689D0,
     *-14.7986D0, 6.47305D0,-69.5323D0, 22.1520D0, 52.2892D0, 21.5826D0,
     * 28.0601D0, 126.223D0, 90.6611D0,-62.7474D0,-3.90579D0, 12.5781D0,
     *-41.3968D0,-51.3376D0,-2.36359D0,-8.88201D0, 96.2748D0,-34.3067D0,
     * 43.7084D0,-345.965D0,-12.3861D0, 7.95582D0,-12.1084D0, 4.58697D0,
     * 18.6063D0,-17.4333D0,-34.1198D0,-190.505D0,-19.6086D0, 6.31289D0,
     * 3.81578D0,-13.7925D0,-15.3793D0, 51.6212D0,-12.2220D0,-7.59584D0,
     * 8.66204D0, 5.23387D0,-8.86539D0, 291.583D0,-10.0384D0, 5.20330D0,
     * 50.3270D0, 5.09435D0,-8.43082D0, 40.0443D0,-16.7649D0, 59.2369D0,
     *-1.86046D0,-29.5331D0,-8.60718D0,-11.8812D0, 4.29660D0, 14.8574D0,
     *-13.7398D0,-13.5452D0,-35.4594D0, 7.09247D0,-23.5664D0,-55.3186D0,
     * 2251.13D0, 152.088D0, 32.2709D0,-1111.48D0, 56.3056D0,-91.6352D0,
     * 37.0407D0,-135.388D0, 556.769D0, 686.311D0, 241.998D0, 141.053D0,
     * 53.9798D0, 11.0326D0, 87.7055D0, 2069.15D0, 540.734D0, 1556.12D0,
     *-192.190D0, 162.743D0, 258.758D0,-213.417D0, 150.489D0,-12.6961D0,
     * 90.0393D0, 844.800D0, 838.494D0, 485.826D0, 137.332D0, 101.685D0,
     * 168.535D0, 75.3540D0, 1505.80D0, 221.107D0, 405.283D0,-6.98117D0,
     *-119.039D0,-961.014D0, 50.1528D0,-8.01811D0,-597.592D0,-346.607D0,
     * 249.011D0, 253.902D0, 66.5097D0, 86.0994D0, 7.30527D0, 100.891D0,
     * 354.646D0, 55.2083D0, 573.265D0,-96.7375D0, 49.5415D0,-3.00164D0,
     *-42.4844D0,-919.866D0,-327.201D0,-120.472D0, 89.9616D0, 57.0413D0,
     *-221.591D0, 291.786D0,-91.9413D0,-259.867D0, 69.1423D0, 273.810D0,
     *-15.8827D0,-18.2359D0,-747.267D0,-722.504D0,-306.676D0, 26.5307D0,
     *-108.648D0,-17.6648D0,-0.820419D0,-1382.64D0,46.4368D0,-280.135D0,
     * 135.013D0, 96.0172D0,-290.440D0,-148.819D0,-66.2665D0, 67.6516D0,
     *-12.2930D0,-272.541D0,-261.413D0, 452.789D0,-186.555D0,-18.0601D0,
     * 48.6234D0,-2.99330D0, 44.3536D0, 204.587D0, 39.7680D0,-78.9640D0,
     *-66.8701D0, 842.817D0, 133.655D0,-167.718D0,-11.1932D0,-92.1422D0,
     *-66.8449D0, 180.287D0,-15.2210D0,-105.889D0, 214.766D0,-448.432D0,
     * 230.265D0,-55.8352D0, 8.33227D0,-55.0245D0, 1232.62D0, 585.938D0,
     * 8.52626D0,-94.4057D0, 368.274D0,-350.322D0, 25.3205D0,-23.2068D0,
     * 290.248D0, 212.799D0,-155.860D0, 159.216D0, 193.656D0, 179.024D0,
     *-3.12968D0, 1.69057D0,-207.967D0, 133.334D0, 239.333D0,-15.4720D0,
     * 9.36480D0,-27.1737D0, 19.8507D0, 194.445D0,-94.0924D0,-109.189D0,
     *-196.369D0,-57.3204D0,-410.475D0,-502.547D0,-94.2240D0, 245.995D0,
     * 102.922D0,-62.5703D0,-174.499D0,-29.7374D0, 658.641D0, 18.7074D0,
     *-377.615D0, 33.6172D0, 59.2858D0,-51.1569D0,-50.8104D0,-542.559D0,
     *-799.378D0, 110.119D0, 34.8633D0, 71.2657D0,-24.0788D0, 200.127D0,
     *-45.3517D0, 22.0259D0,-33.1138D0, 1.97314D0, 26.4956D0,-72.7474D0,
     *-14.8436D0, 15.9802D0, 40.8287D0,-29.1021D0,-25.5842D0, 90.7339D0,
     * 175.167D0,-290.937D0, 214.451D0,-92.7518D0,-116.173D0,-198.670D0,
     *-50.5012D0,-70.6995D0, 348.913D0,-41.9793D0,-23.2414D0, 276.158D0,
     *-104.233D0, 43.5226D0, 74.9910D0, 57.8972D0, 18.8402D0,-88.5617D0,
     *-83.6031D0,-17.7314D0, 73.8449D0, 13.6745D0, 232.231D0, 93.1474D0,
     * 246.798D0, 31.7780D0,-62.3940D0,-11.1797D0, 167.656D0, 30.9078D0,
     *-105.790D0,-358.402D0, 10.2626D0,-241.369D0,-79.1276D0,-14.1222D0,
     * 3.15396D0, 37.5928D0, 126.209D0, 444.117D0,-9.77410D0,-27.1160D0,
     * 114.877D0, 143.705D0,-125.324D0,-73.6348D0, 109.515D0, 13.1847D0,
     * 171.793D0,-25.3481D0,-96.0591D0, 154.742D0,-35.0780D0, 37.7444D0,
     * 40.0519D0,-37.0177D0,-10.7459D0,-139.722D0, 152.131D0,-134.191D0,
     *-13.7317D0,-34.2717D0,-39.8365D0,-122.121D0,-110.150D0, 45.8227D0,
     *-1354.76D0,-197.612D0, 7.46315D0,-29.7226D0, 1491.26D0, 28.7341D0,
     *-174.086D0,-3.89578D0, 371.409D0, 59.0083D0, 13.7102D0, 110.201D0,
     * 44.2579D0,-648.156D0, 537.776D0,-539.161D0, 104.222D0,-1528.88D0,
     *-236.250D0, 5.60413D0,-248.659D0, 561.726D0,-37.0494D0,-193.871D0,
     *-45.9765D0, 445.741D0, 351.702D0,-14.3646D0, 311.593D0, 43.7213D0,
     *-447.759D0, 328.601D0,-411.816D0, 551.639D0,-87.8782D0, 577.467D0,
     * 27.7818D0, 962.880D0,-69.0677D0,-2.43486D0,-362.400D0, 1.52960D0,
     * 15.5608D0, 73.5875D0,-361.893D0, 12.4063D0, 71.9159D0,-7.28626D0,
     * 354.472D0, 345.091D0,-9.40008D0, 377.880D0, 30.3970D0, 126.145D0,
     * 68.3652D0, 263.410D0, 664.261D0, 32.0402D0, 332.664D0,-43.7433D0,
     * 932.734D0,-161.272D0,-27.6409D0, 189.772D0, 150.113D0,-26.5955D0,
     * 128.491D0, 9.19639D0, 30.6587D0,-65.2184D0,-31.1883D0,0.632818D0,
     *-2.12988D0, 51.7718D0, 18.8914D0, 508.824D0, 233.101D0, 381.427D0,
     * 278.877D0, 39.6874D0, 254.790D0,-93.3450D0, 48.2543D0, 137.810D0,
     * 29.7044D0, 180.529D0, 106.820D0, 23.7109D0, 253.284D0, 19.0736D0,
     * 190.699D0,-39.0415D0, 113.439D0, 112.778D0,-137.335D0,-181.616D0,
     * 15.4674D0,-465.053D0,-127.440D0, 2.82314D0, 225.364D0,-24.3936D0,
     * 48.7625D0,-65.8406D0, 14.0144D0, 63.3821D0,-87.5212D0,-10.6907D0,
     * 118.243D0,-3.74233D0,-2.63956D0, 9.57517D0,-272.623D0, 49.7210D0,
     *-277.359D0,-47.9189D0,-70.6913D0, 258.185D0, 439.058D0,-31.0029D0,
     * 292.757D0, 265.861D0, 29.8547D0,-28.7721D0, 98.7536D0,-34.0081D0,
     *-68.8672D0, 5.37649D0, 36.3857D0, 110.176D0, 26.8590D0, 51.4360D0,
     * 11.2919D0,-36.3700D0, 88.7109D0,-75.9456D0, 112.266D0,-241.090D0,
     *-285.362D0, 61.9406D0,-845.873D0, 52.3721D0, 24.3928D0, 234.012D0,
     *-30.8759D0, 13.0416D0,-139.927D0, 17.9904D0, 81.7895D0, 141.421D0,
     *-17.9840D0, 256.052D0,-8.25568D0,-74.3981D0,-191.334D0,-179.696D0,
     * 225.460D0, 173.417D0,-94.2238D0, 16.4143D0, 481.397D0, 408.692D0,
     * 6.89670D0, 236.268D0, 129.491D0, 46.7237D0, 121.047D0, 31.4670D0,
     *-20.4561D0, 191.853D0,-6.59324D0,-131.580D0,-1.32051D0, 247.442D0,
     * 137.977D0, 168.592D0, 123.101D0,-550.961D0,-185.227D0,-7.97620D0,
     * 19.3648D0,-113.024D0,-39.9793D0, 6.26678D0, 13.0142D0, 25.8416D0,
     * 274.646D0, 2.20264D0,-111.250D0, 10.2101D0,-72.1888D0, 331.975D0,
     *-198.694D0, 431.773D0, 120.092D0, 54.1899D0, 17.4340D0, 655.894D0,
     * 133.449D0,-14.8395D0, 319.478D0, 187.130D0,-46.5251D0, 166.447D0,
     * 34.5172D0, 14.5854D0, 114.338D0,-18.6294D0,-30.0081D0,-11.6191D0,
     * 107.410D0,-143.479D0, 223.536D0,-125.027D0, 60.4016D0,-68.5548D0,
     *-12.5562D0,-300.421D0,-57.8429D0, 20.7958D0, 462.685D0, 177.028D0,
     *-6.93411D0,-174.867D0, 59.8222D0, 106.280D0, 134.463D0,-18.2311D0,
     *-354.831D0, 3.80469D0,-192.509D0, 59.2425D0,-357.116D0, 5.35852D0,
     *-18.8169D0,-337.217D0, 42.9243D0, 44.0799D0,-139.315D0,-17.8351D0,
     * 56.5812D0, 14.1176D0,0.248055D0,-21.9830D0, 77.2064D0,0.637791D0,
     * 24.8818D0,-3.46868D0,-17.6312D0,-556.826D0,-8.33638D0,-22.5853D0,
     *-4.00543D0,-128.582D0,-124.997D0,-21.1415D0, 86.6024D0,-149.607D0,
     * 24.0273D0, 9.64333D0, 77.4638D0, 120.541D0, 28.3229D0,-53.4484D0,
     * 13.8874D0, 32.8704D0,-751.765D0, 7.72332D0,-79.3122D0, 2.21472D0,
     *-212.578D0,-98.3487D0,-56.1878D0,-100.124D0,-182.869D0,-50.6402D0,
     *-10.6030D0,-225.666D0,-101.147D0,-4.34860D0,-194.384D0, 19.6370D0,
     * 9.21956D0,-19.5545D0,-275.427D0,-5.35680D0,-238.366D0, 2.55128D0,
     * 46.2323D0,-706.388D0, 11.9831D0,-95.6711D0, 4.77196D0,-234.862D0,
     *-58.6607D0,-72.9478D0,-145.460D0,-213.803D0, 61.1211D0, 14.3983D0,
     *-220.003D0,-55.1937D0, 3.61504D0,-27.0973D0,-261.799D0, 20.4552D0,
     *-263.781D0,-1.20917D0, 8.09824D0, 228.912D0,-9.92299D0, 109.464D0,
     *-0.233977D0, 71.7229D0,79.1259D0,-88.1765D0, 28.8714D0, 231.799D0,
     *-8.20092D0,-7.65327D0,-62.8271D0,-762.473D0,-23.4151D0,-126.459D0,
     *-7.24096D0,-3.02921D0,-583.861D0, 4.70502D0,-87.9273D0, 1.17202D0,
     *-54.1658D0, 29.9435D0, 189.584D0, 29.4832D0,-101.863D0, 147.464D0,
     *-7.22421D0, 2.57149D0,-5.48493D0,-8.95362D0,-7.74990D0,-266.098D0,
     *-9.67699D0,-180.921D0,-0.124553D0,29.4856D0, 355.656D0,-32.6480D0,
     * 98.7496D0,-1.64485D0, 273.565D0, 93.7706D0, 160.255D0, 109.020D0,
     *-147.833D0,-47.9435D0, 27.1415D0, 246.676D0,-48.7877D0, 7.84527D0,
     * 451.210D0,-23.3338D0,-10.2460D0, 45.6456D0,-631.349D0, 12.1430D0,
     * 230.878D0, 4.35478D0,-42.4502D0,-464.214D0, 5.46722D0,-71.7756D0,
     *-0.744062D0, 73.3439D0,72.5351D0, 205.755D0,-82.4280D0, 7.38488D0,
     * 26.8608D0,-16.8157D0,-100.731D0,-5.83024D0,-10.4755D0, 8.95571D0,
     *-145.125D0,-8.48259D0, 97.9517D0,0.658869D0, 44.2689D0, 252.967D0,
     *-23.0178D0, 8.00812D0,0.452745D0, 413.059D0, 150.295D0, 22.0792D0,
     *-123.803D0,-359.656D0,-64.9032D0,-5.76334D0, 18.4593D0,0.725933D0,
     *-10.4014D0,-24.0795D0, 212.340D0,-19.9200D0,-15.7361D0,-8.51025D0,
     * 24.2937D0,-263.434D0,-4.75509D0,-69.0085D0, 1.68477D0,-315.133D0,
     * 40.6424D0,-315.800D0, 46.3927D0, 178.616D0, 53.4077D0, 4.97257D0,
     * 4.07238D0,-278.276D0, 7.50402D0, 284.646D0, 1.36693D0,-28.9062D0,
     *-276.762D0, 5.06325D0,-17.8400D0,0.156077D0, 2.37653D0,-22.2096D0,
     * 21.8721D0,-239.430D0, 38.0253D0,-187.175D0, 8.71422D0,-278.698D0,
     * 39.2467D0, 5.14241D0,-35.7435D0,-184.784D0,-6.60366D0, 193.143D0,
     *-7.23575D0, 11.2310D0,328.499D0,-0.406440D0, 1.41498D0,0.810218D0,
     * 214.073D0, 61.3833D0,-26.9542D0,-119.363D0,-113.010D0,-75.2284D0,
     * 12.7515D0,-176.983D0,105.762D0, -6.50379D0,-58.6124D0, 132.724D0,
     *-6.62143D0, 107.588D0,-16.2588D0, 23.1135D0,-157.380D0,-6.88595D0,
     * 106.704D0,-0.835367D0,-186.721D0, 240.211D0,-271.041D0,214.233D0,
     * 76.4044D0,191.215D0,-13.8258D0,-73.3928D0,  39.2010D0,-1.64763D0/

      XI(1) = XGSW
      XI(2) = YGSW
      XI(3) = ZGSW
      XI(4) = PSI 
      XI(5) = BXIMF_GSW
      XI(6) = BYIMF_GSW
      XI(7) = BZIMF_GSW
      XI(8) = PDYN
      XI(9) = XMS 
      XI(10)= BETA
      CALL MODELVEC (ID,A,XI,F,DERX,DERY,DERZ,IA,960,10,3)
      BX=F(1)
      BY=F(2)
      BZ=F(3)
      RETURN 
      END
C
C==============================================================================
c
      SUBROUTINE MODELVEC (ID,A,XI,F,DERX,DERY,DERZ,IA,NLIN,INDEPVAR,
     * NDEPVAR)
C
C        ***  N.A. Tsyganenko ***  28.10.1997  ***  modified 30.04.2016
C
C  Calculates dependent model variables and their derivatives with respect to
c  both linear and nonlinear parameters, to be used in the RMS minimization procedure.
C
C      Description of parameters:
C
C  ID  - number of a current point from the data set (initial assignments can
c        be made for ID=1 only, saving thus CPU time)
C  A   - input vector containing model parameters;
C  XI  - input vector containing independent variables;
C  F   - output double precision vector containing
C        calculated values of dependent variables;
C  DERX,DERY,DERZ  - output double precision vectors containing
C        calculated values for derivatives of dependent
C        variables with respect to model parameters;
C  IA -  integer vector; IA(L)=0 means that the Lth parameter should be kept
c        fixed in the search, and hence there is no need in calculating
c        derivatives of field components with regard to this parameter;
c        IA(L)=1 means that the derivatives are needed.
c
c  NLIN - total number of coefficients
c
C  ICO - input parameter coded as follows:
c
c       ICO = 0 - derivatives with respect to nonlinear parameters are calculated;
c       ICO = 1 - only derivatives with respect to linear parameters are calculated
C - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
C
      IMPLICIT  REAL * 8  (A - H, O - Z)
C
      PARAMETER (LMIN=0,LMAX=3,NMAX=6)

      DIMENSION F(NDEPVAR),DERX(NLIN),DERY(NLIN),DERZ(NLIN),A(NLIN),
     * XI(INDEPVAR), IA(NLIN)                                
C                                                         
      DIMENSION
     *  BXC_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BXS_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYC_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYS_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZC_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZS_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BXC_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BXS_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYC_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYS_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZC_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZS_POL(LMIN:LMAX,1:NMAX,0:NMAX) 
c
      DATA ALP,EPS /0.56D0,0.186D0/   ! ALP: exponent entering in FPD factor defining B response to Pdyn 
C                                       EPS: exponent entering in the coordinate scaling by Pdyn (FSC)
C      DATA BETA /2.9D0/ ! default for BETA              
C      DATA XMS /5.7D0/  ! default for XMS               
     
      X     = XI(1)   !  UNSCALED GSW COORDS
      Y     = XI(2)   !  UNSCALED GSW COORDS
      Z     = XI(3)   !  UNSCALED GSW COORDS
      PSI   = XI(4)
      BXIMF = XI(5)
      BYIMF = XI(6)
      BZIMF = XI(7)
      PD    = XI(8)
      XMS   = XI(9)
      BETA  = XI(10)

      ID=0   !  means that the point (X,Y,Z) is inside the magnetosheath

      CALL BS (X,Y,Z,PSI,PD,BZIMF,XMS,BETA,RBS,IDBS)      
      IF (IDBS.LT.0) THEN 
      F(1)=BXIMF
      F(2)=BYIMF
      F(3)=BZIMF
      ID=1        ! solar wind
      RETURN
      ENDIF

      PDPM=PD+0.0004*(BXIMF**2+BYIMF**2+BZIMF**2)
      CALL MP (X,Y,Z,PSI,PDPM,BZIMF,RMP,IDMP)
      IF (IDMP.GT.0) THEN
      F(1)=0.D0
      F(2)=0.D0
      F(3)=0.D0
      ID=2        ! magnetosphere
      RETURN
      ENDIF

      FPD   = (PD/1.73D0)**ALP-1.D0    !  1.73 is median value of Pdyn

      FSC   = (PD/2.12D0)**EPS  ! SCALE COORDS BY (PDYN/2.12D0)^EPS  2.12 IS MEAN PDYN
      Xs    = X * FSC
      Ys    = Y * FSC
      Zs    = Z * FSC

      I=0           !   INITIALIZE THE COUNTER OF UNKNOWN LINEAR PARAMETERS

      CALL B_CART(LMIN,LMAX,NMAX,Xs,Ys,Zs,BXC_TOR,BXS_TOR,BYC_TOR,
     * BYS_TOR,BZC_TOR,BZS_TOR,BXC_POL,BXS_POL,BYC_POL,BYS_POL,BZC_POL,
     * BZS_POL)                         

      DO L=LMIN,LMAX          !  ATTENTION: HERE THE DIFFERENCE FROM ALL PREVIOUS VARIANTS
       DO N=1,NMAX     
        DO M=0,N        

        BXCT    = BXC_TOR (L,N,M)
        BYCT    = BYC_TOR (L,N,M)
        BZCT    = BZC_TOR (L,N,M)
        BXST    = BXS_TOR (L,N,M)
        BYST    = BYS_TOR (L,N,M)
        BZST    = BZS_TOR (L,N,M)
        BXCP    = BXC_POL (L,N,M)
        BYCP    = BYC_POL (L,N,M)
        BZCP    = BZC_POL (L,N,M)
        BXSP    = BXS_POL (L,N,M)
        BYSP    = BYS_POL (L,N,M)
        BZSP    = BZS_POL (L,N,M)
C_______________________________________________________________________
C
C  First, for free terms, terms prop to IMF Bz, and terms prop to Psi**2:
c
        IF ((N.GE.1).AND.(MOD(M,2).NE.0)) THEN         

         I=I+1    
         DERX(I) = BXST         ! free term; toroidal part
         DERY(I) = BYST              
         DERZ(I) = BZST                            

         I=I+1    
         DERX(I) = BXST *BZIMF  ! toroidal free term, modulated by BZIMF
         DERY(I) = BYST *BZIMF       
         DERZ(I) = BZST *BZIMF                     

         I=I+1    
         DERX(I) = BXST *FPD    ! toroidal free term, modulated by sw. dyn. pressure
         DERY(I) = BYST *FPD              
         DERZ(I) = BZST *FPD                            

         I=I+1    
         DERX(I) = BXST *BZIMF *FPD  ! toroidal free term, modulated by product of BZIMF and FPD
         DERY(I) = BYST *BZIMF *FPD       
         DERZ(I) = BZST *BZIMF *FPD                     

         I=I+1    
         DERX(I) = BXST *PSI**2   !  toroidal free term, modulated by symmetric contribution from dipole tilt
         DERY(I) = BYST *PSI**2      
         DERZ(I) = BZST *PSI**2
c ---------------------------------------------------------------------
         I=I+1    
         DERX(I) = BXCP           ! free term; poloidal part
         DERY(I) = BYCP              
         DERZ(I) = BZCP                            

         I=I+1    
         DERX(I) = BXCP *BZIMF  ! poloidal free term, modulated by BZIMF
         DERY(I) = BYCP *BZIMF       
         DERZ(I) = BZCP *BZIMF                     

         I=I+1    
         DERX(I) = BXCP *FPD    ! poloidal free term, modulated by sw. dyn. pressure
         DERY(I) = BYCP *FPD              
         DERZ(I) = BZCP *FPD                            

         I=I+1    
         DERX(I) = BXCP *BZIMF *FPD  ! poloidal free term, modulated by product of BZIMF and FPD
         DERY(I) = BYCP *BZIMF *FPD       
         DERZ(I) = BZCP *BZIMF *FPD                     

         I=I+1    
         DERX(I) = BXCP *PSI**2   !  poloidal free term, modulated by symmetric contribution from dipole tilt
         DERY(I) = BYCP *PSI**2      
         DERZ(I) = BZCP *PSI**2
C_______________________________________________________________________
c
C  Next, for terms prop to IMF By (which are nonzero for the same set of N-M combinations):
c
         I=I+1    
         DERX(I) = BXCT *BYIMF
         DERY(I) = BYCT *BYIMF       
         DERZ(I) = BZCT *BYIMF                     

         I=I+1    
         DERX(I) = BXCT *BYIMF *FPD
         DERY(I) = BYCT *BYIMF *FPD       
         DERZ(I) = BZCT *BYIMF *FPD                     

         I=I+1    
         DERX(I) = BXSP *BYIMF 
         DERY(I) = BYSP *BYIMF       
         DERZ(I) = BZSP *BYIMF 

         I=I+1    
         DERX(I) = BXSP *BYIMF *FPD 
         DERY(I) = BYSP *BYIMF *FPD       
         DERZ(I) = BZSP *BYIMF *FPD 

        ENDIF
C_______________________________________________________________________
c
c  Now, for terms prop to IMF Bx and PSI:
c
        IF ((N.GE.2).AND.(MOD(M,2).EQ.0).AND.M.GE.2) THEN         
      
         I=I+1    
         DERX(I) = BXST *BXIMF
         DERY(I) = BYST *BXIMF       
         DERZ(I) = BZST *BXIMF                     

         I=I+1    
         DERX(I) = BXST *BXIMF *FPD
         DERY(I) = BYST *BXIMF *FPD       
         DERZ(I) = BZST *BXIMF *FPD                     

         I=I+1    
         DERX(I) = BXST *PSI   
         DERY(I) = BYST *PSI         
         DERZ(I) = BZST *PSI   

        ENDIF

        IF ((N.GE.1).AND.(MOD(M,2).EQ.0)) THEN         
      
         I=I+1    
         DERX(I) = BXCP *BXIMF
         DERY(I) = BYCP *BXIMF       
         DERZ(I) = BZCP *BXIMF                     

         I=I+1    
         DERX(I) = BXCP *BXIMF *FPD
         DERY(I) = BYCP *BXIMF *FPD       
         DERZ(I) = BZCP *BXIMF *FPD                    

         I=I+1    
         DERX(I) = BXCP *PSI   
         DERY(I) = BYCP *PSI         
         DERZ(I) = BZCP *PSI   

        ENDIF
c
        ENDDO
       ENDDO
      ENDDO
C
C -------------   TOTAL FIELD: ----------------------------------------------------------
C
         F(1)=0.D0
         F(2)=0.D0
         F(3)=0.D0

         DO 100 I=1,NLIN
          F(1)=F(1)+A(I)*DERX(I)
          F(2)=F(2)+A(I)*DERY(I)
 100      F(3)=F(3)+A(I)*DERZ(I)
C
      RETURN
      END
C========================================================================================
C               
      SUBROUTINE MP (X,Y,Z,PSI,PDPM,BZIMF,RMP,ID)
C
c     Based on magnetopause model by Lin et al., 2010;  some details are eliminated (such as dayside indentations and tilt-independent asymmetry terms)
c     
c     Input:  X,Y,Z (in Re, GSM or GSE, does not matter, since the model BS shape is assumed axisymmetric around X)
c             PSI (tilt angle in radians; again, here does not affect anything due to the symmetry)
c             PDPM (ram pressure from OMNI + magnetic pressure 0.0004*B_imf**2)
c             BZIMF
c
c     Output: RMP (geocentric distance to the magnetopause in the direction of the {X,Y,Z} point
c             ID (position flag; equals 1 or -1, if the {X,Y,Z} point is inside or outside the M.P., resp.)
c
      IMPLICIT REAL*8 (A-H,O-Z)
      DIMENSION AA(22)
C
      DATA A0,A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,A11,A12,A13,A14,A15,A16,
     * A17,A18,A19,A20,A21/12.544D0,-0.194D0,0.305D0,0.0573D0,2.178D0,
     * 0.0571D0,-0.999D0,16.473D0,0.00152D0,0.382D0,0.0431D0,-0.00763D0,
     *-0.210D0,0.0405D0,-4.430D0,-0.636D0,-2.600D0,0.832D0,-5.328D0,
     * 1.103D0,-0.907D0,1.450D0/    !   ORIGINAL VALUES OF LIN ET AL MODEL PARAMETERS
C
c      A10=0.D0  ! remove overall dawn-dusk asymmetry (unrelated to tilt, nor to any other parameters)
c      A11=0.D0  ! remove overall north-south asymmetry (unrelated to tilt, nor to any other parameters)
c      A12=0.D0  ! retain overall north-south asymmetry, controlled by the dipole tilt angle
c      A13=0.D0  ! remove oblateness of the boundary (unrelated to tilt, nor to any other parameters)
c      A14=0.D0  !  ELIMINATE THE INDENTATION TERMS
C
      EN=A21
      ES=A21
      THETAN=A19+A20*PSI
      THETAS=A19-A20*PSI
      CTN=DCOS(THETAN)
      CTS=DCOS(THETAS)
      STN=DSIN(THETAN)
      STS=DSIN(THETAS)

      RHO2=Y**2+Z**2
      R=DSQRT(X**2+RHO2)
      RHO=DSQRT(RHO2)

      IF (RHO.GT.1.D-8) THEN  ! WE ARE NOT ON THE X-AXIS - NO SINGULARITIES TO WORRY ABOUT
        CT=X/R
        ST=RHO/R
        T=DATAN2(ST,CT)
        SP=Z/RHO
        CP=Y/RHO
      ELSE                      !   ON THE X-AXIS
        IF (X.GT.0.D0) THEN     !   ON THE DAYSIDE
         CT=X/R
         ST=1.0D-8/R            !   SET RHO=10^-8, TO AVOID SINGULARITY OF GRAD_FI (IF MODE=1, SEE GRADFIP=... BELOW)
         T=DATAN2(ST,CT)
         SP=0.D0
         CP=1.D0
        ELSE                    !  ON THE TAIL AXIS; TO AVOID SINGULARITY:
         RM=1000.D0             !  ASSIGN RM=1000 (A CONVENTIONAL SUBSTITUTE VALUE)
         RETURN                 !  AND EXIT
        ENDIF
      ENDIF

      BRN=CT*CTN+ST*STN*SP
      PSIN=DACOS(BRN)
      BRS=CT*CTS-ST*STS*SP
      PSIS=DACOS(BRS)

      DN=A16+(A17+A18*PSI)*PSI
      DS=A16-(A17-A18*PSI)*PSI

      CN=A14*PDPM**A15
      CS=CN

      B0=A6+A7*(DEXP(A8*BZIMF)-1.D0)/(DEXP(A9*BZIMF)+1.D0)
      B1=A10
      B2=A11+A12*PSI
      B3=A13
      BETA=B0+B1*CP+B2*SP+B3*SP**2
      BRF=DSQRT(0.5D0*(1.D0+CT))+A5*2.D0*ST*CT*(1.D0-DEXP(-T))

      F=BRF**BETA
      R0=A0*PDPM**A1*(1.D0+A2*(DEXP(A3*BZIMF)
     *   -1.D0)/(DEXP(A4*BZIMF)+1.D0))
      RMP=R0*F+CN*DEXP(DN*PSIN**EN)+CS*DEXP(DS*PSIS**ES)

      ID=1
      IF (RMP.LT.R) ID=-1

      FI=R-RMP

      RETURN
      END
C
C========================================================================================
C                    
      SUBROUTINE BS (X,Y,Z,PSI,PD,BZIMF,XMS,BETA,RBS,ID)   ! XMS & BETA are magnetosonic Mach number & plasma beta (from OMNI)
C
c     Based on bow shock model by Lu et al., 2019;
c     
c     Input:  X,Y,Z (in Re, GSM or GSE, does not matter, since the model BS shape is assumed axisymmetric around X)
c             PSI (tilt angle in radians; again, here does not affect anything due to the symmetry)
c             PD (ram pressure from OMNI; not sure if Lu et al. included the alpha-particle component)
c             BZIMF
c             BETA (plasma beta)
c
c     Output: RBS (geocentric distance to the B.S. in the direction of the {X,Y,Z} point
c             ID (position flag; equals 1 or -1, if the {X,Y,Z} point is inside or outside the BS, resp.
c
      IMPLICIT REAL*8 (A-H,O-Z)
      DIMENSION AA(20)
C
      DATA A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,A11,A12,A13,A14,A15,A16,A17,
     * A18,A19,A20/13.132D0,4.5875D0,.0016D0,.3341D0,6.1115D0,18.9096D0,
     *0.3029D0,0.0429D0,-0.0056D0,-0.0072D0,-0.0054D0,-0.0019D0,.0217D0,
     *0.1479D0,0.0241D0,0.0842D0,0.0094D0,0.0908D0,0.0682D0,0.0398D0/

c      A11=0.D0; A12=0.D0; A15=0.D0; A16=0.D0   !  remove tilt-dependent and tilt-independent asymmetries
c      A17=0.D0; A18=0.D0; A19=0.D0; A20=0.D0   !  remove tilt-dependent and tilt-independent asymmetries
C
      PS=PSI      !     assume that Psi are in radians (not clear from the LU's paper)
C           NOTE OF 12/08/22: BASED ON THE VALUE OF A4 IN LU's PAPER, PSI IS, OF COURSE, IN RADIANS, NOT DEGS!
c
      ALPHA0=A6*(1.D0+A7*DSIGN(1.D0,BZIMF)*DTANH(A8*BZIMF))*(1.D0+A9*PD)
     * *(1.D0+A10*DLOG(BETA))*(A11*PS**2+A12*PS+A13)*(1.D0+A14*XMS)
      ALPHA1=A15*PS**2+A16*PS+A17
      ALPHA2=A18*PS**2+A19*PS+A20

      RHO2=Y**2+Z**2
      R=DSQRT(X**2+RHO2)
      RHO=DSQRT(RHO2)

      IF (RHO.GT.1.D-8) THEN  ! WE ARE NOT ON THE X-AXIS - NO SINGULARITIES TO WORRY ABOUT
        CT=X/R
        ST=RHO/R
        T=DATAN2(ST,CT)
        CP=Z/RHO
      ELSE                      !   ON THE X-AXIS
        IF (X.GT.0.D0) THEN     !   ON THE DAYSIDE
         CT=X/R
         ST=1.0D-8/R            !   SET RHO=10^-8, TO AVOID SINGULARITY OF GRAD_FI (IF MODE=1, SEE GRADFIP=... BELOW)
         T=DATAN2(ST,CT)
         CP=1.D0
        ELSE                    !  ON THE TAIL AXIS; TO AVOID SINGULARITY:
         RM=1000.D0             !  ASSIGN RM=1000 (A CONVENTIONAL SUBSTITUTE VALUE)
         RETURN                 !  AND EXIT
        ENDIF
      ENDIF

      R0=A1*(1.D0+A2/XMS**2)*(1.D0+A3/BETA)*(1.D0+A4*PS**2)
     *  *PD**(-1.D0/A5)
      RBS=R0*(2.D0/(1.D0+CT))**(ALPHA0+ALPHA1*CP+ALPHA2*CP**2)

      ID=1
      IF (RBS.LT.R) ID=-1

      RETURN
      END
c
C========================================================================================== 
C
      SUBROUTINE LEGENDASS (N,M,T,PNM,DPNMDT,D2PNMDT2)
      IMPLICIT REAL*8 (A-H,O-Z)
C
C  EQUATIONS BASED ON LANGEL, CH.4, P.259;  WORKS FOR N<=6 (and M<=N)
c  DERIVATIVES OBTAINED FROM https://www.derivative-calculator.net/
C
C  INPUT : N,M - order and degree indices of Pnm;  C & S are cos(theta) & sin(theta), resp.
c  OUTPUT: PNM,DPNMDT,D2PNMDT2
      
       DIMENSION FN(28)   
C
c      DATA FN     
c     * /3*1.D0,0.5D0,2*3.D0,0.5D0,1.5D0,2*15.D0,0.125D0,2.5D0,7.5D0, !  normalization factors
c     *  2*105.D0,0.375D0,1.875D0,2*52.5D0,2*945.D0,0.0625D0,2.625D0, !   (Neumann's variant) (adopted from Langel, Table 4, p.259)
c     *  13.125D0,157.5D0,472.5D0,2*10395.D0/

      DATA FN/.100000000000000D+01,.100000000000000D+01,              ! normalization factors by Schmidt
     *.100000000000000D+01,.500000000000000D+00,.173205080756888D+01, !  (calculated following Table 4 (p.259)
     *.866025403784439D+00,.500000000000000D+00,.612372435695794D+00, !    of Bob Langel's book; for some unknown reason, 
     *.193649167310371D+01,.790569415042095D+00,.125000000000000D+00, !    they are different from those in REC array
     *.790569415042095D+00,.559016994374947D+00,.209165006633519D+01, !     in RECALC_08 of GEOPACK)
     *.739509972887452D+00,.375000000000000D+00,.484122918275927D+00,
     *.256173769148990D+01,.522912516583797D+00,.221852991866236D+01,
     *.701560760020114D+00,.625000000000000D-01,.572821961869480D+00,
     *.452855523318420D+00,.905711046636840D+00,.496078370824611D+00,
     *.232681380862329D+01,.671693289381396D+00/

      C=DCOS(T)
      S=DSIN(T)

      IF (N.EQ.0.AND.M.EQ.0) THEN  !  this case does not actually come about
       PNM     =0.D0
       DPNMDT  =0.D0
       D2PNMDT2=0.D0
      ENDIF
      IF (N.EQ.1.AND.M.EQ.0) THEN
       PNM     = C
       DPNMDT  =-S
       D2PNMDT2=-C
      ENDIF
      IF (N.EQ.1.AND.M.EQ.1) THEN
       PNM     = S
       DPNMDT  = C
       D2PNMDT2=-S
      ENDIF
      IF (N.EQ.2.AND.M.EQ.0) THEN
       PNM     = 3.D0*C**2-1.D0
       DPNMDT  =-6.D0*C*S
       D2PNMDT2= 6.D0*(S**2-C**2)
      ENDIF
      IF (N.EQ.2.AND.M.EQ.1) THEN
       PNM     = C*S
       DPNMDT  = C**2-S**2
       D2PNMDT2=-4.D0*S*C
      ENDIF
      IF (N.EQ.2.AND.M.EQ.2) THEN
       PNM     = S**2
       DPNMDT  = 2.D0*S*C
       D2PNMDT2= 2.D0*(C**2-S**2)
      ENDIF
  
      IF (N.EQ.3.AND.M.EQ.0) THEN
       PNM     = 5.D0*C**3-3.D0*C
       DPNMDT  = 3.D0*S*(1.D0-5.D0*C**2)
       D2PNMDT2= 3.D0*C*(10.D0*S**2-5.D0*C**2+1.D0)
      ENDIF
  
      IF (N.EQ.3.AND.M.EQ.1) THEN
       PNM     = S*(5.D0*C**2-1.D0)
       DPNMDT  = C*(5.D0*C**2-10.D0*S**2-1.D0)
       D2PNMDT2= 10.D0*S**3+S*(1.D0-35.D0*C**2)
      ENDIF
  
      IF (N.EQ.3.AND.M.EQ.2) THEN
       PNM     = S**2*C
       DPNMDT  = S*(2.D0*C**2-S**2)
       D2PNMDT2= C*(9.D0*C**2-7.D0)
      ENDIF
  
      IF (N.EQ.3.AND.M.EQ.3) THEN
       PNM     = S**3
       DPNMDT  = 3.D0*C*S**2
       D2PNMDT2= 3.D0*S*(2.D0*C**2-S**2)
      ENDIF
  
      IF (N.EQ.4.AND.M.EQ.0) THEN
       PNM     = 35.D0*C**4-30.D0*C**2+3.D0
       DPNMDT  = 20.D0*C*S*(3.D0-7.D0*C**2)
       D2PNMDT2= 20.D0*C**2*(3.D0-7.D0*C**2)+S**2*(7.D0*C**2-1.D0)*60.D0
      ENDIF
  
      IF (N.EQ.4.AND.M.EQ.1) THEN
       PNM     = C*S*(7.D0*C**2-3.D0)
       DPNMDT  = 3.D0*S**2*(1.D0-7.D0*C**2)+C**2*(7.D0*C**2-3.D0)
       D2PNMDT2= 2.D0*C*S*(21.D0*S**2-35.D0*C**2+6.D0)
      ENDIF
  
      IF (N.EQ.4.AND.M.EQ.2) THEN
       PNM     = S**2*(7.D0*C**2-1.D0)
       DPNMDT  = 2.D0*C*S*(7.D0*C**2-7.D0*S**2-1.D0)
       D2PNMDT2= 14.D0*(S**4+C**4)+S**2*(2.D0-84.D0*C**2)-2.D0*C**2
      ENDIF
  
      IF (N.EQ.4.AND.M.EQ.3) THEN
       PNM     = S**3*C
       DPNMDT  = S**2*(3.D0*C**2-S**2)
       D2PNMDT2= 2.D0*S*C*(3.D0*C**2-5.D0*S**2)
      ENDIF
  
      IF (N.EQ.4.AND.M.EQ.4) THEN
       PNM     = S**4
       DPNMDT  = 4.D0*S**3*C
       D2PNMDT2= 4.D0*S**2*(3.D0*C**2-S**2) 
      ENDIF
  
      IF (N.EQ.5.AND.M.EQ.0) THEN
       PNM     = 21.D0*C**5-70.D0/3.D0*C**3+5.D0*C
       DPNMDT  = S*(70.D0*C**2-105.D0*C**4-5.D0)
       D2PNMDT2= 5.D0*C*((84.D0*C**2-28.D0)*S**2-21.D0*C**4
     *  +14.D0*C**2-1.D0)
      ENDIF
  
      IF (N.EQ.5.AND.M.EQ.1) THEN
       PNM     = S*(21.D0*C**4-14.D0*C**2+1.D0)
       DPNMDT  = C*(21.D0*C**4-S**2*(84.D0*C**2-28.D0)-14.D0*C**2+1.D0)
       D2PNMDT2= S**3*(252.D0*C**2-28.D0)+S*(98.D0*C**2
     *  -273.D0*C**4-1.D0)
      ENDIF
  
      IF (N.EQ.5.AND.M.EQ.2) THEN
       PNM     = S**2*(3.D0*C**3-C)
       DPNMDT  = S**3*(1.D0-9.D0*C**2)+2.D0*S*C**2*(3.D0*C**2-1.D0)
       D2PNMDT2= C*(18.D0*S**4+(7.D0-51.D0*C**2)*S**2+6.D0*C**4
     * -2.D0*C**2)
      ENDIF
  
      IF (N.EQ.5.AND.M.EQ.3) THEN
       PNM     = S**3*(9.D0*C**2-1.D0)
       DPNMDT  = 3.D0*C*S**2*(9.D0*C**2-6.D0*S**2-1.D0)
       D2PNMDT2= 18.D0*S**5+S**3*(3.D0-153.D0*C**2)+S*(54.D0*C**4
     *  -6.D0*C**2)
      ENDIF
  
      IF (N.EQ.5.AND.M.EQ.4) THEN
       PNM     = S**4*C
       DPNMDT  = S**3*(4.D0*C**2-S**2)
       D2PNMDT2= S**2*C*(12.D0*C**2-13.D0*S**2)
      ENDIF
  
      IF (N.EQ.5.AND.M.EQ.5) THEN
       PNM     = S**5
       DPNMDT  = 5.D0*C*S**4
       D2PNMDT2= 5.D0*S**3*(4.D0*C**2-S**2)
      ENDIF
  
      IF (N.EQ.6.AND.M.EQ.0) THEN
       PNM     = 231.D0*C**6-315.D0*C**4+105.D0*C**2-5.D0
       DPNMDT  = S*C*(-1386.D0*C**4+1260.D0*C**2-210.D0)
       D2PNMDT2= S**2*(6930.D0*C**4-3780.D0*C**2+210.D0)-1386.D0*C**6
     *  +1260.D0*C**4-210.D0*C**2
      ENDIF
  
      IF (N.EQ.6.AND.M.EQ.1) THEN
       PNM     = S*(33.D0*C**5-30.D0*C**3+5.D0*C)
       DPNMDT  = S**2*(90.D0*C**2-165.D0*C**4-5.D0)+33.D0*C**6
     *  -30.D0*C**4+5.D0*C**2
       D2PNMDT2= 4.D0*C*S*(S**2*(165.D0*C**2-45.D0)-132.D0*C**4
     *  +75.D0*C**2-5.D0)
      ENDIF
  
      IF (N.EQ.6.AND.M.EQ.2) THEN
       PNM     = S**2*(33.D0*C**4-18.D0*C**2+1.D0)
       DPNMDT  =-2.D0*C*S*(S**2*(66.D0*C**2-18.D0)-33.D0*C**4
     *  +18.D0*C**2-1.D0) 
       D2PNMDT2= S**4*(396.D0*C**2-36.D0)+S**2*(216.D0*C**2-726.D0*C**4
     *  -2.D0)+66.D0*C**6-36.D0*C**4+2.D0*C**2
      ENDIF
  
      IF (N.EQ.6.AND.M.EQ.3) THEN
       PNM     = S**3*(11.D0*C**3-3.D0*C)
       DPNMDT  = S**4*(3.D0-33.D0*C**2)+S**2*(33.D0*C**4-9.D0*C**2)
       D2PNMDT2= 6.D0*C*S*(11.D0*S**4+S**2*(5.D0-44.D0*C**2)+11.D0*C**4
     *  -3.D0*C**2)
      ENDIF
  
      IF (N.EQ.6.AND.M.EQ.4) THEN
       PNM     = S**4*(11.D0*C**2-1.D0)
       DPNMDT  = 2.D0*C*S**3*(22.D0*C**2-11.D0*S**2-2.D0)
       D2PNMDT2= 22.D0*S**6+S**4*(4.D0-242.D0*C**2)+S**2*(132.D0*C**4
     *  -12.D0*C**2)
      ENDIF
  
      IF (N.EQ.6.AND.M.EQ.5) THEN
       PNM     = S**5*C
       DPNMDT  = S**4*(5.D0*C**2-S**2)
       D2PNMDT2= S**3*C*(20.D0*C**2-16.D0*S**2)
      ENDIF
  
      IF (N.EQ.6.AND.M.EQ.6) THEN
       PNM     = S**6
       DPNMDT  = 6.D0*C*S**5
       D2PNMDT2= 6.D0*S**4*(5.D0*C**2-S**2) 
      ENDIF

      IND=(N*(N+1))/2+M+1
      PNM     =PNM     *FN(IND)
      DPNMDT  =DPNMDT  *FN(IND)
      D2PNMDT2=D2PNMDT2*FN(IND)

      RETURN
      END
C_________________________________________________________________________________
c
      SUBROUTINE B_CART(LMIN,LMAX,NMAX,X,Y,Z,BXC_TOR,BXS_TOR,BYC_TOR,
     * BYS_TOR,BZC_TOR,BZS_TOR,BXC_POL,BXS_POL,BYC_POL,BYS_POL,BZC_POL,
     * BZS_POL)                         
      IMPLICIT REAL*8 (A-H,O-Z)

      DIMENSION
     *  BXC_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BXS_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYC_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYS_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZC_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZS_TOR(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BXC_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BXS_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYC_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BYS_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZC_POL(LMIN:LMAX,1:NMAX,0:NMAX),
     *  BZS_POL(LMIN:LMAX,1:NMAX,0:NMAX) 

       DATA AL/0.5D0/,RS0/12.D0/     !  AL defines tail expansion rate;  AL=0.5 corresponds to cylindrical tail

       RHO=SQRT(Y**2+Z**2)
       R=SQRT(X**2+Y**2+Z**2)
       IF (RHO.LT.1.D-8) RHO=1.D-8
       ST=RHO/R
       CT=X/R
       T=DATAN2(ST,CT)
       IF (RHO.GT.1.D-8) THEN
        P=DATAN2(Y,Z) ! needed for CM & SM below
       ELSE
        P=0.D0
       ENDIF
       CP=COS(P)     ! needed for converting from sph. to cart. in the end
       SP=SIN(P)     ! needed for converting from sph. to cart. in the end

       DO L=LMIN,LMAX   !  Note: L is the exponent in coefficient expansions in L powers

       DO N=1,NMAX
       DO M=0,N

       CALL LEGENDASS(N,M,T,PNM,DPNMDT,D2PNMDT2)

       CM=COS(M*P)
       SM=SIN(M*P)

       YNM_C     = PNM*CM
       YNM_S     = PNM*SM
       DYNMDT_C  = DPNMDT*CM
       DYNMDT_S  = DPNMDT*SM
       DYNMDP_C  =-PNM*SM*M
       DYNMDP_S  = PNM*CM*M
       D2YNMDT2_C= D2PNMDT2*CM
       D2YNMDT2_S= D2PNMDT2*SM
       D2YNMDP2_C=-M**2*YNM_C
       D2YNMDP2_S=-M**2*YNM_S

       D2YNMDTDP_C=-DPNMDT*M*SM
       D2YNMDTDP_S= DPNMDT*M*CM

       CHT=COS(0.5D0*T)
       THT=TAN(0.5D0*T)

       RS = R*((1.D0+CT)/2.D0)**AL   ! RS is the standoff distance coordinate, corresponding to given r=R and theta=T

       D    = 1.D0-RS/RS0
       DDDR = (D-1.D0)/R
       DDDT = AL*(1.D0-D)*THT
       D2DDT2  = AL*((1.D0-D)/(2.D0*CHT**2)-DDDT*THT)
       D2DDRDT = DDDT/R
c
c  Polo (C):
C
      IF (L.EQ.0) THEN
       D_PSIP_DR   =0.D0
       D_PSIP_DT   =DYNMDT_C
       D_PSIP_DP   =DYNMDP_C
       D2_PSIP_DR2 =0.D0
       D2_PSIP_DRDT=0.D0
       D2_PSIP_DRDP=0.D0
       D2_PSIP_DT2 =D2YNMDT2_C
       D2_PSIP_DTDP=D2YNMDTDP_C
       D2_PSIP_DP2 =D2YNMDP2_C
      ENDIF

      IF (L.EQ.1) THEN
       D_PSIP_DR   =DDDR*YNM_C
       D_PSIP_DT   =D*DYNMDT_C+DDDT*YNM_C
       D_PSIP_DP   =D*DYNMDP_C
       D2_PSIP_DR2 =0.D0
       D2_PSIP_DRDT=DDDR*DYNMDT_C+D2DDRDT*YNM_C
       D2_PSIP_DRDP=DDDR*DYNMDP_C
       D2_PSIP_DT2 =D2DDT2*YNM_C+2.D0*DDDT*DYNMDT_C+D*D2YNMDT2_C
       D2_PSIP_DTDP=DDDT*DYNMDP_C+D*D2YNMDTDP_C
       D2_PSIP_DP2 =D*D2YNMDP2_C
      ENDIF

      IF (L.EQ.2) THEN
       D_PSIP_DR   =2.D0*D*DDDR*YNM_C
       D_PSIP_DT   =D*(2.D0*DDDT*YNM_C+D*DYNMDT_C)
       D_PSIP_DP   =D**2*DYNMDP_C
       D2_PSIP_DR2 =2.D0*DDDR**2*YNM_C
       D2_PSIP_DRDT=2.D0*(DDDR*(DDDT*YNM_C+D*DYNMDT_C)+D*D2DDRDT*YNM_C)
       D2_PSIP_DRDP=2.D0*D*DDDR*DYNMDP_C                 
       D2_PSIP_DT2 =2.D0*YNM_C*(DDDT**2+D*D2DDT2)+D*(4.D0*DDDT*DYNMDT_C
     *  +D*D2YNMDT2_C)
       D2_PSIP_DTDP=D*(D*D2YNMDTDP_C+2.D0*DDDT*DYNMDP_C)
       D2_PSIP_DP2 =D**2*D2YNMDP2_C
      ENDIF

      IF (L.EQ.3) THEN                    
       D_PSIP_DR   =3.D0*D**2*DDDR*YNM_C
       D_PSIP_DT   =D**2*(3.D0*DDDT*YNM_C+D*DYNMDT_C)
       D_PSIP_DP   =D**3*DYNMDP_C
       D2_PSIP_DR2 =6.D0*D*DDDR**2*YNM_C
       D2_PSIP_DRDT=3.D0*D*((2.D0*DDDR*DDDT+D*D2DDRDT)*YNM_C
     *  +D*DDDR*DYNMDT_C)
       D2_PSIP_DRDP=3.D0*D**2*DDDR*DYNMDP_C                 
       D2_PSIP_DT2 =3.D0*D*(YNM_C*(2.D0*DDDT**2+D*D2DDT2)
     *  +2.D0*D*DDDT*DYNMDT_C)+D**3*D2YNMDT2_C
       D2_PSIP_DTDP=D**2*(3.D0*DDDT*DYNMDP_C+D*D2YNMDTDP_C)
       D2_PSIP_DP2 =D**3*D2YNMDP2_C
      ENDIF

      BRC_POL=(D2_PSIP_DRDT*DDDT+D_PSIP_DR*D2DDT2-D2_PSIP_DT2*DDDR
     * -D_PSIP_DT*D2DDRDT+CT/ST*(D_PSIP_DR*DDDT-D_PSIP_DT*DDDR)
     * -DDDR*D2_PSIP_DP2/ST**2)/R**2

      BTC_POL=-(D2_PSIP_DP2/R**2*DDDT/ST**2+D2_PSIP_DR2*DDDT
     *  +D_PSIP_DR*D2DDRDT-D2_PSIP_DRDT*DDDR)/R

      BPC_POL=(D2_PSIP_DRDP*DDDR+(D2_PSIP_DTDP*DDDT+D_PSIP_DP*D2DDT2
     *-CT/ST*D_PSIP_DP*DDDT)/R**2)/(R*ST)
C
C  Toro (C):
C
      BRC_TOR=-D_PSIP_DP*DDDT/(R**2*ST)
      BTC_TOR= D_PSIP_DP*DDDR/(R*ST)     
      BPC_TOR=(D_PSIP_DR*DDDT-D_PSIP_DT*DDDR)/R     
c
c  Polo (S):
C
      IF (L.EQ.0) THEN
       D_PSIP_DR   =0.D0
       D_PSIP_DT   =DYNMDT_S
       D_PSIP_DP   =DYNMDP_S
       D2_PSIP_DR2 =0.D0
       D2_PSIP_DRDT=0.D0
       D2_PSIP_DRDP=0.D0
       D2_PSIP_DT2 =D2YNMDT2_S
       D2_PSIP_DTDP=D2YNMDTDP_S
       D2_PSIP_DP2 =D2YNMDP2_S
      ENDIF

      IF (L.EQ.1) THEN
       D_PSIP_DR   =DDDR*YNM_S
       D_PSIP_DT   =D*DYNMDT_S+DDDT*YNM_S
       D_PSIP_DP   =D*DYNMDP_S
       D2_PSIP_DR2 =0.D0
       D2_PSIP_DRDT=DDDR*DYNMDT_S+D2DDRDT*YNM_S
       D2_PSIP_DRDP=DDDR*DYNMDP_S
       D2_PSIP_DT2 =D2DDT2*YNM_S+2.D0*DDDT*DYNMDT_S+D*D2YNMDT2_S
       D2_PSIP_DTDP=DDDT*DYNMDP_S+D*D2YNMDTDP_S
       D2_PSIP_DP2 =D*D2YNMDP2_S
      ENDIF

      IF (L.EQ.2) THEN
       D_PSIP_DR   =2.D0*D*DDDR*YNM_S
       D_PSIP_DT   =D*(2.D0*DDDT*YNM_S+D*DYNMDT_S)
       D_PSIP_DP   =D**2*DYNMDP_S
       D2_PSIP_DR2 =2.D0*DDDR**2*YNM_S
       D2_PSIP_DRDT=2.D0*(DDDR*(DDDT*YNM_S+D*DYNMDT_S)+D*D2DDRDT*YNM_S)
       D2_PSIP_DRDP=2.D0*D*DDDR*DYNMDP_S                 
       D2_PSIP_DT2 =2.D0*YNM_S*(DDDT**2+D*D2DDT2)+D*(4.D0*DDDT*DYNMDT_S
     *  +D*D2YNMDT2_S)
       D2_PSIP_DTDP=D*(D*D2YNMDTDP_S+2.D0*DDDT*DYNMDP_S)
       D2_PSIP_DP2 =D**2*D2YNMDP2_S
      ENDIF

      IF (L.EQ.3) THEN                                               
       D_PSIP_DR   =3.D0*D**2*DDDR*YNM_S
       D_PSIP_DT   =D**2*(3.D0*DDDT*YNM_S+D*DYNMDT_S)
       D_PSIP_DP   =D**3*DYNMDP_S
       D2_PSIP_DR2 =6.D0*D*DDDR**2*YNM_S
       D2_PSIP_DRDT=3.D0*D*((2.D0*DDDR*DDDT+D*D2DDRDT)*YNM_S
     *  +D*DDDR*DYNMDT_S)
       D2_PSIP_DRDP=3.D0*D**2*DDDR*DYNMDP_S                 
       D2_PSIP_DT2 =3.D0*D*(YNM_S*(2.D0*DDDT**2+D*D2DDT2)
     *  +2.D0*D*DDDT*DYNMDT_S)+D**3*D2YNMDT2_S
       D2_PSIP_DTDP=D**2*(3.D0*DDDT*DYNMDP_S+D*D2YNMDTDP_S)
       D2_PSIP_DP2 =D**3*D2YNMDP2_S
      ENDIF

      BRS_POL=(D2_PSIP_DRDT*DDDT+D_PSIP_DR*D2DDT2-D2_PSIP_DT2*DDDR
     * -D_PSIP_DT*D2DDRDT+CT/ST*(D_PSIP_DR*DDDT-D_PSIP_DT*DDDR)
     * -DDDR*D2_PSIP_DP2/ST**2)/R**2

      BTS_POL=-(D2_PSIP_DP2/R**2*DDDT/ST**2+D2_PSIP_DR2*DDDT
     *  +D_PSIP_DR*D2DDRDT-D2_PSIP_DRDT*DDDR)/R

      BPS_POL=(D2_PSIP_DRDP*DDDR+(D2_PSIP_DTDP*DDDT+D_PSIP_DP*D2DDT2
     *-CT/ST*D_PSIP_DP*DDDT)/R**2)/(R*ST)
C
c  Toro (S):
c
      BRS_TOR=-D_PSIP_DP*DDDT/(R**2*ST)
      BTS_TOR= D_PSIP_DP*DDDR/(R*ST)     
      BPS_TOR=(D_PSIP_DR*DDDT-D_PSIP_DT*DDDR)/R     
c
c  Convert to Cartesian:
c
      BT=BRC_TOR*ST+BTC_TOR*CT
      BXC_TOR(L,N,M)=BRC_TOR*CT-BTC_TOR*ST
      BYC_TOR(L,N,M)=BT*SP+BPC_TOR*CP 
      BZC_TOR(L,N,M)=BT*CP-BPC_TOR*SP 

      BT=BRS_TOR*ST+BTS_TOR*CT
      BXS_TOR(L,N,M)=BRS_TOR*CT-BTS_TOR*ST
      BYS_TOR(L,N,M)=BT*SP+BPS_TOR*CP 
      BZS_TOR(L,N,M)=BT*CP-BPS_TOR*SP 

      BT=BRC_POL*ST+BTC_POL*CT
      BXC_POL(L,N,M)=BRC_POL*CT-BTC_POL*ST
      BYC_POL(L,N,M)=BT*SP+BPC_POL*CP 
      BZC_POL(L,N,M)=BT*CP-BPC_POL*SP 

      BT=BRS_POL*ST+BTS_POL*CT
      BXS_POL(L,N,M)=BRS_POL*CT-BTS_POL*ST
      BYS_POL(L,N,M)=BT*SP+BPS_POL*CP 
      BZS_POL(L,N,M)=BT*CP-BPS_POL*SP 

      ENDDO
      ENDDO
      ENDDO

      RETURN
      END
C

program msh23_wrapper
  implicit none
  integer :: ios
  real*8 :: xgsw, ygsw, zgsw, psi, pdyn, xms, beta
  real*8 :: bximf, byimf, bzimf, bx, by, bz
  integer :: id
  
  do while (.true.)
    read(*, *, iostat=ios) xgsw, ygsw, zgsw, psi, pdyn, bximf, byimf, bzimf
    if (ios /= 0) exit
    
    xms = 5.7d0
    beta = 2.9d0
    
    call magnetosheath_b(xgsw, ygsw, zgsw, psi, pdyn, xms, beta, &
                         bximf, byimf, bzimf, id, bx, by, bz)
    write(*, '(I2,3F12.4)') id, bx, by, bz
  end do
end program msh23_wrapper

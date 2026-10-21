from .models import Profile

def profile():
    profiles = Profile.objects.count()
    
    print(profiles)
    
profile()
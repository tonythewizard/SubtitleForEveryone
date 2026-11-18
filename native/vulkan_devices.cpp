#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <cstdio>
#include <vector>

int main() {
    HMODULE vulkan = LoadLibraryExW(L"vulkan-1.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!vulkan) return 0;

    auto get = reinterpret_cast<PFN_vkGetInstanceProcAddr>(GetProcAddress(vulkan, "vkGetInstanceProcAddr"));
    if (!get) return 1;
    auto create = reinterpret_cast<PFN_vkCreateInstance>(get(nullptr, "vkCreateInstance"));
    if (!create) return 1;
    VkInstanceCreateInfo options{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    VkInstance instance = VK_NULL_HANDLE;
    if (create(&options, nullptr, &instance) != VK_SUCCESS) return 1;

    auto enumerate = reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(get(instance, "vkEnumeratePhysicalDevices"));
    auto properties = reinterpret_cast<PFN_vkGetPhysicalDeviceProperties>(get(instance, "vkGetPhysicalDeviceProperties"));
    auto destroy = reinterpret_cast<PFN_vkDestroyInstance>(get(instance, "vkDestroyInstance"));
    uint32_t count = 0;
    if (enumerate && properties && enumerate(instance, &count, nullptr) == VK_SUCCESS && count) {
        std::vector<VkPhysicalDevice> devices(count);
        if (enumerate(instance, &count, devices.data()) == VK_SUCCESS) {
            for (uint32_t index = 0; index < count; ++index) {
                VkPhysicalDeviceProperties info{};
                properties(devices[index], &info);
                std::printf("%u\t%s\n", index, info.deviceName);
            }
        }
    }
    if (destroy) destroy(instance, nullptr);
    FreeLibrary(vulkan);
    return 0;
}

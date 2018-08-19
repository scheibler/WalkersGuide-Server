import java.io.IOException;
import java.lang.Throwable;
import java.util.Date;
import java.util.EnumSet;
import java.util.List;

import de.schildbach.pte.NetworkProvider;
import de.schildbach.pte.NetworkProvider.Accessibility;
import de.schildbach.pte.NetworkProvider.Optimize;
import de.schildbach.pte.NetworkProvider.WalkSpeed;
import de.schildbach.pte.dto.Location;
import de.schildbach.pte.dto.LocationType;
import de.schildbach.pte.dto.NearbyLocationsResult;
import de.schildbach.pte.dto.Product;
import de.schildbach.pte.dto.QueryDeparturesResult;
import de.schildbach.pte.dto.QueryTripsResult;

import de.schildbach.pte.BahnProvider;
import de.schildbach.pte.VbbProvider;
import de.schildbach.pte.VvoProvider;

public class QueryData {

    private static final String VBB_IDENTIFIER = "vbb";
    private static final String VVO_IDENTIFIER = "vvo";

    public Location createAddressObject(int latitude, int longitude) {
        return new Location(LocationType.ADDRESS, null, latitude, longitude);
    }

    public QueryTripsResult calculateConnection(
            String providerIdentifier, Location from, Location to, int delay) {
        NetworkProvider provider = this.getProvider(providerIdentifier);
        Date departureDate = new Date( System.currentTimeMillis() + delay*60000 );
        try {
            QueryTripsResult result = provider.queryTrips(
                    from, null, to, departureDate, true, Product.ALL, Optimize.LEAST_CHANGES,
                    WalkSpeed.SLOW, Accessibility.NEUTRAL, null);
            // try to get some more trips
            if (result != null && result.context.canQueryLater()) {
                QueryTripsResult laterResult = provider.queryMoreTrips(result.context, true);
                if (laterResult != null) {
                    for (int i=0; i<laterResult.trips.size(); i++) {
                        result.trips.add(laterResult.trips.get(i));
                    }
                }
            }
            return result;
        } catch (IOException | IllegalStateException | NullPointerException e) {
            System.out.println("queryTrips error: " + e.getMessage());
            e.printStackTrace();
            return null;
        }        
    }

    public QueryDeparturesResult getDepartures(String providerIdentifier, String stationID) {
        System.out.println("station id: " + stationID);
        NetworkProvider provider = this.getProvider(providerIdentifier);
        try {
            return provider.queryDepartures(stationID, new Date(), 0, false);
        } catch (IOException e) {
            System.out.println("getDepartures error: " + e.getMessage());
            e.printStackTrace();
            return null;
        }        
    }

    public NearbyLocationsResult getNearestStations(
            String providerIdentifier, int latitude, int longitude) {
        NetworkProvider provider = this.getProvider(providerIdentifier);
        try {
            return provider.queryNearbyLocations(
                    EnumSet.of(LocationType.STATION), Location.coord(latitude, longitude), 250, 10);
        } catch (IOException e) {
            System.out.println("getNearestStations error: " + e.getMessage());
            e.printStackTrace();
            return null;
        }        
    }

    private NetworkProvider getProvider(String identifier) {
        if (identifier != null && identifier.equals(VBB_IDENTIFIER)) {
            return new VbbProvider();
        } else if (identifier != null && identifier.equals(VVO_IDENTIFIER)) {
            return new VvoProvider();
        } else {
            return new BahnProvider();
        }
    }

}

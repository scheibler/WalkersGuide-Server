import java.io.IOException;
import java.util.Date;
import java.util.EnumSet;
import java.util.List;

import de.schildbach.pte.BahnProvider;
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

public class QueryData {

    private NetworkProvider provider;

    public QueryData() {
        this.provider = new BahnProvider();
    }

    public Location createAddressObject(int latitude, int longitude) {
        return new Location(LocationType.ADDRESS, null, latitude, longitude);
    }

    public QueryTripsResult calculateConnection(Location from, Location to, int delay) {
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
        } catch (IOException e) {
            return null;
        } catch (IllegalStateException e) {
            return null;
        } catch (NullPointerException e) {
            return null;
        }        
    }

    public QueryDeparturesResult getDepartures(String stationID) {
        try {
            return provider.queryDepartures(stationID,
                    new Date( System.currentTimeMillis()), 0, false);
        } catch (IOException e) {
            return null;
        }        
    }

    public NearbyLocationsResult getNearestStations(int latitude, int longitude) {
        try {
            return provider.queryNearbyLocations(
                    EnumSet.of(LocationType.STATION), Location.coord(latitude, longitude), 0, 0);
        } catch (IOException e) {
            return null;
        }        
    }

}
